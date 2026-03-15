"""
Base class for all supply chain AI agents.
Provides Claude API integration, retry logic, metrics, and Slack notifications.
"""
import time
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
import structlog
import anthropic
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from prometheus_client import Counter, Histogram

from app.core.config import settings
from app.core.slack_notifier import SlackNotifier, SlackLevel

logger = structlog.get_logger()

# Prometheus metrics for agents
agent_requests = Counter(
    "agent_requests_total", "Total agent requests", ["agent_name", "status"]
)
agent_latency = Histogram(
    "agent_request_duration_seconds",
    "Agent request latency",
    ["agent_name"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)
agent_token_usage = Counter(
    "agent_tokens_total", "Total tokens consumed by agent", ["agent_name", "token_type"]
)


class BaseAgent(ABC):
    """
    Abstract base class for all supply chain AI agents.

    Provides:
    - Claude API integration with retry logic
    - Prometheus metrics tracking
    - Slack notification integration
    - Agentic tool-use loop
    - Structured logging
    """

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.CLAUDE_MODEL
        self.max_tokens = settings.CLAUDE_MAX_TOKENS
        self.slack = SlackNotifier()
        self.tools = self._define_tools()
        self._request_count = 0
        self._success_count = 0
        self._total_latency_ms = 0.0

    @abstractmethod
    def _define_tools(self) -> List[Dict]:
        """Define Claude tools (function calling) for this agent."""
        pass

    @abstractmethod
    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Process a supply chain task and return structured result."""
        pass

    def _get_system_prompt(self) -> str:
        """Return the system prompt for this agent."""
        return f"""You are {self.name}, a specialized AI agent in a supply chain management platform.
Your role: {self.description}

You have access to tools that interact with the supply chain database and external services.
Always use the available tools to get real data before making recommendations.
Be precise, data-driven, and action-oriented in your responses.
Format monetary values with currency codes. Use ISO dates.
Flag any anomalies or urgent issues immediately."""

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.APITimeoutError)),
        reraise=True,
    )
    def _call_claude_sync(
        self, messages: List[Dict], system: Optional[str] = None
    ) -> anthropic.types.Message:
        """Make a synchronous Claude API call with retry logic."""
        kwargs = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if self.tools:
            kwargs["tools"] = self.tools

        return self.client.messages.create(**kwargs)

    async def call_claude(
        self, messages: List[Dict], system: Optional[str] = None
    ) -> anthropic.types.Message:
        """Async wrapper for Claude API call with metrics."""
        start_time = time.time()
        self._request_count += 1

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: self._call_claude_sync(messages, system or self._get_system_prompt())
            )

            # Track token usage
            if hasattr(response, "usage"):
                agent_token_usage.labels(
                    agent_name=self.name, token_type="input"
                ).inc(response.usage.input_tokens)
                agent_token_usage.labels(
                    agent_name=self.name, token_type="output"
                ).inc(response.usage.output_tokens)

            self._success_count += 1
            agent_requests.labels(agent_name=self.name, status="success").inc()
            return response

        except Exception as e:
            agent_requests.labels(agent_name=self.name, status="error").inc()
            logger.error("Claude API call failed", agent=self.name, error=str(e))
            raise
        finally:
            elapsed_ms = (time.time() - start_time) * 1000
            self._total_latency_ms += elapsed_ms
            agent_latency.labels(agent_name=self.name).observe(elapsed_ms / 1000)

    async def run_agentic_loop(
        self,
        initial_messages: List[Dict],
        tool_handler,
        system: Optional[str] = None,
        max_iterations: int = 10,
    ) -> Tuple[str, List[Dict]]:
        """
        Run the full agentic tool-use loop until stop_reason == 'end_turn'.

        Args:
            initial_messages: Starting messages
            tool_handler: Async function that handles tool_use blocks
            system: System prompt override
            max_iterations: Maximum number of tool call iterations

        Returns:
            Tuple of (final_text_response, message_history)
        """
        messages = initial_messages.copy()
        iteration = 0
        final_text = ""

        while iteration < max_iterations:
            iteration += 1
            response = await self.call_claude(messages, system)

            # Collect text from response
            text_blocks = [b.text for b in response.content if b.type == "text"]
            if text_blocks:
                final_text = "\n".join(text_blocks)

            if response.stop_reason == "end_turn":
                break

            if response.stop_reason == "tool_use":
                # Process tool calls
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        logger.debug(
                            "Agent calling tool",
                            agent=self.name,
                            tool=block.name,
                            iteration=iteration,
                        )
                        result = await tool_handler(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": str(result),
                        })

                # Add assistant response and tool results to message history
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
            else:
                break

        return final_text, messages

    async def notify_slack(
        self,
        message: str,
        level: SlackLevel = SlackLevel.INFO,
        title: Optional[str] = None,
    ) -> None:
        """Send Slack notification from this agent."""
        await self.slack.send(
            message=f"[{self.name}] {message}",
            level=level,
            title=title or self.name,
        )

    def get_status(self) -> Dict[str, Any]:
        """Return agent health/status metrics."""
        success_rate = (
            self._success_count / self._request_count if self._request_count > 0 else 1.0
        )
        avg_latency = (
            self._total_latency_ms / self._request_count if self._request_count > 0 else 0.0
        )
        return {
            "name": self.name,
            "description": self.description,
            "model": self.model,
            "status": "active",
            "total_requests": self._request_count,
            "success_rate": round(success_rate, 4),
            "avg_latency_ms": round(avg_latency, 2),
        }
