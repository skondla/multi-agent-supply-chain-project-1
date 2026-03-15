"""LLMOps: Per-agent token consumption and cost attribution."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Anthropic Claude pricing (per million tokens, as of 2024)
PRICING = {
    "claude-opus-4-6": {
        "input": 15.00,   # $15 per 1M input tokens
        "output": 75.00,  # $75 per 1M output tokens
    },
    "claude-sonnet-4-6": {
        "input": 3.00,
        "output": 15.00,
    },
    "claude-haiku-4-5-20251001": {
        "input": 0.25,
        "output": 1.25,
    },
}

DEFAULT_MODEL = "claude-opus-4-6"


class TokenUsage:
    """Token usage record for a single agent invocation."""

    def __init__(
        self,
        agent_name: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        task_type: str = "unknown",
        request_id: str | None = None,
    ):
        self.agent_name = agent_name
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.total_tokens = input_tokens + output_tokens
        self.task_type = task_type
        self.request_id = request_id
        self.timestamp = datetime.now(timezone.utc)

        pricing = PRICING.get(model, PRICING[DEFAULT_MODEL])
        self.input_cost = (input_tokens / 1_000_000) * pricing["input"]
        self.output_cost = (output_tokens / 1_000_000) * pricing["output"]
        self.total_cost = self.input_cost + self.output_cost

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "input_cost_usd": round(self.input_cost, 6),
            "output_cost_usd": round(self.output_cost, 6),
            "total_cost_usd": round(self.total_cost, 6),
            "task_type": self.task_type,
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat(),
        }


class CostTracker:
    """Track and attribute LLM token costs per agent, task type, and time period."""

    def __init__(self, daily_budget_usd: float = 500.0):
        self.daily_budget_usd = daily_budget_usd
        self._records: list[TokenUsage] = []
        self._agent_totals: dict[str, dict] = defaultdict(
            lambda: {"input_tokens": 0, "output_tokens": 0, "total_cost": 0.0, "requests": 0}
        )

    def record(
        self,
        agent_name: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        task_type: str = "unknown",
        request_id: str | None = None,
    ) -> TokenUsage:
        """Record token usage and compute costs."""
        usage = TokenUsage(
            agent_name=agent_name,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            task_type=task_type,
            request_id=request_id,
        )
        self._records.append(usage)

        # Update agent totals
        totals = self._agent_totals[agent_name]
        totals["input_tokens"] += input_tokens
        totals["output_tokens"] += output_tokens
        totals["total_cost"] += usage.total_cost
        totals["requests"] += 1

        # Trim old records (keep last 100k)
        if len(self._records) > 100_000:
            self._records = self._records[-50_000:]

        logger.info(
            "token_usage_recorded",
            agent=agent_name,
            model=model,
            tokens=usage.total_tokens,
            cost_usd=round(usage.total_cost, 4),
        )

        # Check budget
        daily_cost = self.get_daily_cost()
        if daily_cost > self.daily_budget_usd * 0.80:
            logger.warning(
                "approaching_daily_budget",
                daily_cost=daily_cost,
                budget=self.daily_budget_usd,
                percentage=round(daily_cost / self.daily_budget_usd * 100, 1),
            )

        return usage

    def get_daily_cost(self) -> float:
        """Get total cost for today (UTC)."""
        today = datetime.now(timezone.utc).date()
        return sum(
            r.total_cost for r in self._records
            if r.timestamp.date() == today
        )

    def get_agent_summary(self) -> dict[str, dict]:
        """Get cost and token summary per agent."""
        result = {}
        for agent_name, totals in self._agent_totals.items():
            result[agent_name] = {
                **totals,
                "avg_cost_per_request": (
                    totals["total_cost"] / totals["requests"]
                    if totals["requests"] > 0 else 0
                ),
            }
        return result

    def get_hourly_costs(self, hours: int = 24) -> list[dict]:
        """Get hourly cost breakdown for the last N hours."""
        from collections import Counter
        hourly: dict[str, float] = defaultdict(float)
        for record in self._records:
            hour_key = record.timestamp.strftime("%Y-%m-%d %H:00")
            hourly[hour_key] += record.total_cost

        return [
            {"hour": hour, "cost_usd": round(cost, 4)}
            for hour, cost in sorted(hourly.items())[-hours:]
        ]

    def get_task_type_breakdown(self) -> dict[str, dict]:
        """Get cost breakdown by task type."""
        breakdown: dict[str, dict] = defaultdict(
            lambda: {"requests": 0, "tokens": 0, "cost_usd": 0.0}
        )
        for record in self._records:
            entry = breakdown[record.task_type]
            entry["requests"] += 1
            entry["tokens"] += record.total_tokens
            entry["cost_usd"] += record.total_cost

        return {k: {**v, "cost_usd": round(v["cost_usd"], 4)} for k, v in breakdown.items()}

    def get_dashboard_metrics(self) -> dict:
        """Get all metrics for the monitoring dashboard."""
        return {
            "daily_cost_usd": round(self.get_daily_cost(), 4),
            "daily_budget_usd": self.daily_budget_usd,
            "budget_utilization_pct": round(
                self.get_daily_cost() / self.daily_budget_usd * 100, 1
            ),
            "total_requests": len(self._records),
            "agent_summary": self.get_agent_summary(),
            "hourly_costs": self.get_hourly_costs(24),
            "task_breakdown": self.get_task_type_breakdown(),
        }


# Singleton
_tracker: CostTracker | None = None


def get_cost_tracker() -> CostTracker:
    global _tracker
    if _tracker is None:
        from app.core.config import settings
        budget = getattr(settings, "llm_daily_budget_usd", 500.0)
        _tracker = CostTracker(daily_budget_usd=budget)
    return _tracker
