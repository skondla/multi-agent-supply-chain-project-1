"""LLMOps: Prompt injection detection, output filtering, and rate limiting."""
from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# ── Prompt Injection Patterns ─────────────────────────────────────────────────
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"disregard\s+(all\s+)?(previous|prior)\s+(instructions?|context)",
    r"you\s+are\s+now\s+(a|an|acting\s+as)",
    r"forget\s+(everything|all|your|the)\s+(above|previous|prior|instructions?)",
    r"new\s+instructions?:",
    r"system\s*:\s*you",
    r"\[INST\]",
    r"<\|system\|>",
    r"jailbreak",
    r"dan\s*mode",
    r"developer\s+mode",
    r"bypass\s+(safety|filter|guardrail)",
    r"pretend\s+(you\s+are|to\s+be)",
    r"roleplay\s+as",
    r"act\s+as\s+if\s+you\s+(have\s+no|don't\s+have)",
]

COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in INJECTION_PATTERNS]

# ── PII Patterns ──────────────────────────────────────────────────────────────
PII_PATTERNS = {
    "credit_card": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "phone": re.compile(r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "api_key": re.compile(r"\b(?:sk-ant|sk-|api[-_]?key[-_]?)[a-zA-Z0-9]{20,}\b", re.IGNORECASE),
}


class GuardrailResult:
    """Result of a guardrail check."""

    def __init__(self, passed: bool, reason: str = "", risk_score: float = 0.0):
        self.passed = passed
        self.reason = reason
        self.risk_score = risk_score
        self.violations: list[str] = []

    def add_violation(self, violation: str) -> None:
        self.violations.append(violation)
        self.passed = False


class RateLimiter:
    """Token bucket rate limiter per user/agent."""

    def __init__(self, requests_per_minute: int = 60, requests_per_hour: int = 1000):
        self.rpm = requests_per_minute
        self.rph = requests_per_hour
        self._minute_windows: dict[str, deque] = defaultdict(deque)
        self._hour_windows: dict[str, deque] = defaultdict(deque)

    def check(self, key: str) -> tuple[bool, str]:
        """Check if request is allowed. Returns (allowed, reason)."""
        now = time.time()

        # Clean old entries
        minute_window = self._minute_windows[key]
        hour_window = self._hour_windows[key]

        while minute_window and now - minute_window[0] > 60:
            minute_window.popleft()
        while hour_window and now - hour_window[0] > 3600:
            hour_window.popleft()

        # Check limits
        if len(minute_window) >= self.rpm:
            return False, f"Rate limit exceeded: {self.rpm} requests/minute"

        if len(hour_window) >= self.rph:
            return False, f"Rate limit exceeded: {self.rph} requests/hour"

        # Record request
        minute_window.append(now)
        hour_window.append(now)
        return True, ""


class InputGuardrail:
    """Validate and sanitize user inputs before sending to LLM."""

    def __init__(self, max_input_length: int = 10_000):
        self.max_input_length = max_input_length
        self.rate_limiter = RateLimiter()

    def check(self, text: str, user_id: str = "anonymous", context: dict | None = None) -> GuardrailResult:
        """Run all input guardrail checks."""
        result = GuardrailResult(passed=True)

        # Length check
        if len(text) > self.max_input_length:
            result.add_violation(f"Input too long: {len(text)} > {self.max_input_length} chars")
            result.risk_score = max(result.risk_score, 0.3)

        # Rate limiting
        allowed, reason = self.rate_limiter.check(user_id)
        if not allowed:
            result.add_violation(reason)
            result.risk_score = max(result.risk_score, 0.5)

        # Prompt injection detection
        for pattern in COMPILED_PATTERNS:
            if pattern.search(text):
                result.add_violation(f"Potential prompt injection: matched '{pattern.pattern[:50]}'")
                result.risk_score = max(result.risk_score, 0.9)
                break

        # PII detection in user input (warn but don't block)
        for pii_type, pattern in PII_PATTERNS.items():
            if pii_type in ("api_key",) and pattern.search(text):
                result.add_violation(f"Potential {pii_type} detected in input")
                result.risk_score = max(result.risk_score, 0.7)

        if not result.passed:
            logger.warning(
                "input_guardrail_triggered",
                user_id=user_id,
                violations=result.violations,
                risk_score=result.risk_score,
            )

        return result


class OutputGuardrail:
    """Filter and sanitize LLM outputs before returning to users."""

    def check(self, text: str, context: dict | None = None) -> GuardrailResult:
        """Run all output guardrail checks."""
        result = GuardrailResult(passed=True)
        sanitized = text

        # PII redaction in output
        for pii_type, pattern in PII_PATTERNS.items():
            if pii_type == "api_key":
                sanitized = pattern.sub("[REDACTED_API_KEY]", sanitized)
            elif pii_type == "credit_card":
                sanitized = pattern.sub("[REDACTED_CC]", sanitized)
            elif pii_type == "ssn":
                sanitized = pattern.sub("[REDACTED_SSN]", sanitized)

        # Check for harmful content indicators
        harmful_patterns = [
            r"(?:password|secret|token|key)\s*[:=]\s*\S+",
        ]
        for pattern in harmful_patterns:
            if re.search(pattern, sanitized, re.IGNORECASE):
                result.add_violation("Potential sensitive data in output")
                result.risk_score = max(result.risk_score, 0.6)

        result.sanitized_text = sanitized
        return result


class GuardrailMiddleware:
    """Combined guardrail middleware for the supply chain AI platform."""

    def __init__(self):
        self.input_guard = InputGuardrail()
        self.output_guard = OutputGuardrail()
        self._blocked_count = 0
        self._total_count = 0

    def validate_input(self, text: str, user_id: str = "anonymous") -> GuardrailResult:
        """Validate input before sending to agent."""
        self._total_count += 1
        result = self.input_guard.check(text, user_id)
        if not result.passed:
            self._blocked_count += 1
        return result

    def filter_output(self, text: str) -> GuardrailResult:
        """Filter and sanitize agent output."""
        return self.output_guard.check(text)

    def get_stats(self) -> dict:
        return {
            "total_requests": self._total_count,
            "blocked_requests": self._blocked_count,
            "block_rate": (
                self._blocked_count / self._total_count
                if self._total_count > 0 else 0.0
            ),
        }


# Singleton
_middleware: GuardrailMiddleware | None = None


def get_guardrails() -> GuardrailMiddleware:
    global _middleware
    if _middleware is None:
        _middleware = GuardrailMiddleware()
    return _middleware
