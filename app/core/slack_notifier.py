"""
Slack notification service for supply chain alerts and events.
"""
import asyncio
from enum import Enum
from typing import List, Optional
import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger()


class SlackLevel(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


LEVEL_COLORS = {
    SlackLevel.INFO: "#36a64f",
    SlackLevel.SUCCESS: "#2ecc71",
    SlackLevel.WARNING: "#f39c12",
    SlackLevel.ERROR: "#e74c3c",
    SlackLevel.CRITICAL: "#8e44ad",
}

LEVEL_ICONS = {
    SlackLevel.INFO: ":information_source:",
    SlackLevel.SUCCESS: ":white_check_mark:",
    SlackLevel.WARNING: ":warning:",
    SlackLevel.ERROR: ":x:",
    SlackLevel.CRITICAL: ":rotating_light:",
}


class SlackNotifier:
    """Async Slack notifier via webhook or Bot API."""

    def __init__(self):
        self.webhook_url = settings.SLACK_WEBHOOK_URL
        self.default_channel = settings.SLACK_CHANNEL
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def send(
        self,
        message: str,
        level: SlackLevel = SlackLevel.INFO,
        channel: Optional[str] = None,
        title: Optional[str] = None,
        fields: Optional[List[dict]] = None,
        footer: Optional[str] = None,
    ) -> bool:
        """Send a formatted Slack notification."""
        if not self.webhook_url:
            logger.debug("Slack webhook not configured, skipping notification")
            return False

        color = LEVEL_COLORS.get(level, "#36a64f")
        icon = LEVEL_ICONS.get(level, ":bell:")

        attachment = {
            "color": color,
            "text": f"{icon} {message}",
            "footer": footer or f"Supply Chain AI | {settings.APP_ENV}",
            "ts": int(asyncio.get_event_loop().time()),
        }

        if title:
            attachment["title"] = title

        if fields:
            attachment["fields"] = [
                {"title": f["title"], "value": f["value"], "short": f.get("short", True)}
                for f in fields
            ]

        payload = {
            "channel": channel or self.default_channel,
            "attachments": [attachment],
        }

        try:
            client = await self._get_client()
            response = await client.post(self.webhook_url, json=payload)
            response.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("Failed to send Slack notification", error=str(e))
            return False

    async def send_deployment_notification(
        self, version: str, environment: str, status: str, actor: str
    ) -> bool:
        """Send a deployment status notification."""
        level = SlackLevel.SUCCESS if status == "success" else SlackLevel.ERROR
        return await self.send(
            message=f"Deployment *{status}* for version `{version}` to *{environment}*",
            level=level,
            title="Deployment Notification",
            fields=[
                {"title": "Version", "value": version},
                {"title": "Environment", "value": environment},
                {"title": "Status", "value": status},
                {"title": "Actor", "value": actor},
            ],
        )

    async def send_alert(self, alert_type: str, message: str, severity: str) -> bool:
        """Send a supply chain alert."""
        level_map = {
            "low": SlackLevel.INFO,
            "medium": SlackLevel.WARNING,
            "high": SlackLevel.ERROR,
            "critical": SlackLevel.CRITICAL,
        }
        return await self.send(
            message=message,
            level=level_map.get(severity, SlackLevel.WARNING),
            title=f"Supply Chain Alert: {alert_type}",
            fields=[
                {"title": "Alert Type", "value": alert_type},
                {"title": "Severity", "value": severity.upper()},
            ],
        )

    async def send_agent_notification(
        self, agent_name: str, task: str, status: str, details: Optional[str] = None
    ) -> bool:
        """Send an agent activity notification."""
        level = SlackLevel.SUCCESS if status == "completed" else SlackLevel.WARNING
        message = f"Agent `{agent_name}` {status} task: {task}"
        if details:
            message += f"\n{details}"
        return await self.send(message=message, level=level, title="Agent Activity")

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Global notifier instance
notifier = SlackNotifier()
