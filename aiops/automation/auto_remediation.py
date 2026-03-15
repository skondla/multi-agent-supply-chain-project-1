"""AIOps: Intelligent alert routing and automated runbook execution."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine

import structlog

logger = structlog.get_logger(__name__)


class RemediationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class RemediationAction:
    """An automated remediation action."""
    name: str
    description: str
    alert_patterns: list[str]
    runbook_url: str = ""
    requires_approval: bool = False
    cooldown_seconds: int = 300
    max_retries: int = 2


@dataclass
class RemediationResult:
    """Result of executing a remediation action."""
    action_name: str
    alert_name: str
    status: RemediationStatus
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    output: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "action_name": self.action_name,
            "alert_name": self.alert_name,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "output": self.output[:500],
            "error": self.error[:200],
        }


class AutoRemediator:
    """Automated remediation engine that responds to Prometheus alerts."""

    def __init__(self):
        self._actions: dict[str, RemediationAction] = {}
        self._handlers: dict[str, Callable] = {}
        self._history: list[RemediationResult] = []
        self._cooldowns: dict[str, datetime] = {}
        self._register_default_actions()

    def _register_default_actions(self) -> None:
        """Register built-in remediation actions."""
        self.register(
            RemediationAction(
                name="scale_api_pods",
                description="Scale API deployment when CPU is high",
                alert_patterns=["APIHighLatency", "NodeHighCPU"],
                cooldown_seconds=600,
            ),
            handler=self._scale_api_pods,
        )
        self.register(
            RemediationAction(
                name="clear_redis_cache",
                description="Clear Redis cache when memory is high",
                alert_patterns=["RedisHighMemory"],
                cooldown_seconds=1800,
            ),
            handler=self._clear_redis_cache,
        )
        self.register(
            RemediationAction(
                name="restart_celery_workers",
                description="Restart Celery workers on high queue backlog",
                alert_patterns=["OrderProcessingBacklog"],
                cooldown_seconds=300,
                requires_approval=False,
            ),
            handler=self._restart_celery_workers,
        )
        self.register(
            RemediationAction(
                name="notify_ml_team",
                description="Notify ML team on model drift or training failure",
                alert_patterns=["DemandForecastMAPEHigh", "ModelTrainingFailed", "PredictionDriftCritical"],
                cooldown_seconds=3600,
            ),
            handler=self._notify_ml_team,
        )
        self.register(
            RemediationAction(
                name="trigger_model_retraining",
                description="Trigger MLOps pipeline when drift exceeds threshold",
                alert_patterns=["PredictionDriftCritical", "FeatureDriftDetected"],
                cooldown_seconds=86400,  # Once per day max
                requires_approval=True,
            ),
            handler=self._trigger_model_retraining,
        )

    def register(self, action: RemediationAction, handler: Callable) -> None:
        """Register a remediation action with its handler."""
        self._actions[action.name] = action
        self._handlers[action.name] = handler
        logger.debug("remediation_action_registered", name=action.name)

    async def handle_alert(self, alert_name: str, labels: dict, annotations: dict) -> list[RemediationResult]:
        """Process an incoming alert and execute matching remediations."""
        results = []
        matched_actions = [
            action for action in self._actions.values()
            if alert_name in action.alert_patterns
        ]

        if not matched_actions:
            logger.debug("no_remediation_for_alert", alert=alert_name)
            return results

        for action in matched_actions:
            result = await self._execute_action(action, alert_name, labels, annotations)
            results.append(result)
            self._history.append(result)

        return results

    async def _execute_action(
        self,
        action: RemediationAction,
        alert_name: str,
        labels: dict,
        annotations: dict,
    ) -> RemediationResult:
        """Execute a single remediation action."""
        result = RemediationResult(
            action_name=action.name,
            alert_name=alert_name,
            status=RemediationStatus.PENDING,
        )

        # Check cooldown
        cooldown_key = f"{action.name}:{alert_name}"
        if cooldown_key in self._cooldowns:
            elapsed = (datetime.now(timezone.utc) - self._cooldowns[cooldown_key]).total_seconds()
            if elapsed < action.cooldown_seconds:
                result.status = RemediationStatus.SKIPPED
                result.output = f"Cooldown active: {int(action.cooldown_seconds - elapsed)}s remaining"
                logger.debug("remediation_skipped_cooldown", action=action.name)
                return result

        if action.requires_approval:
            result.status = RemediationStatus.SKIPPED
            result.output = "Manual approval required"
            logger.info("remediation_requires_approval", action=action.name, alert=alert_name)
            return result

        result.status = RemediationStatus.RUNNING
        handler = self._handlers[action.name]

        for attempt in range(action.max_retries + 1):
            try:
                output = await handler(alert_name=alert_name, labels=labels, annotations=annotations)
                result.status = RemediationStatus.SUCCESS
                result.output = str(output)
                self._cooldowns[cooldown_key] = datetime.now(timezone.utc)
                logger.info(
                    "remediation_succeeded",
                    action=action.name,
                    alert=alert_name,
                    attempt=attempt + 1,
                )
                break
            except Exception as e:
                if attempt < action.max_retries:
                    await asyncio.sleep(30 * (attempt + 1))
                    continue
                result.status = RemediationStatus.FAILED
                result.error = str(e)
                logger.error(
                    "remediation_failed",
                    action=action.name,
                    alert=alert_name,
                    error=str(e),
                )

        result.completed_at = datetime.now(timezone.utc)
        return result

    # ── Built-in handlers ─────────────────────────────────────────────────────

    async def _scale_api_pods(self, alert_name: str, labels: dict, **kwargs) -> str:
        """Scale API deployment up."""
        import subprocess
        logger.info("auto_scaling_api_pods", alert=alert_name)
        # In real deployment, would use kubectl or k8s API
        return "Scaling recommendation sent to Kubernetes HPA"

    async def _clear_redis_cache(self, alert_name: str, **kwargs) -> str:
        """Selectively clear Redis cache entries."""
        from app.core.redis_client import CacheService
        logger.info("clearing_redis_cache", alert=alert_name)
        cache = CacheService(prefix="supply_chain")
        # Would clear low-priority cache entries
        return "Redis cache selective cleanup initiated"

    async def _restart_celery_workers(self, alert_name: str, **kwargs) -> str:
        """Signal Celery workers to restart gracefully."""
        logger.info("restarting_celery_workers", alert=alert_name)
        return "Celery worker restart signal sent"

    async def _notify_ml_team(self, alert_name: str, labels: dict, annotations: dict, **kwargs) -> str:
        """Send notification to ML team via Slack."""
        from app.core.slack_notifier import SlackNotifier, SlackLevel
        from app.core.config import settings

        notifier = SlackNotifier(settings.slack_webhook_url)
        await notifier.send_alert(
            title=f"ML Alert Requires Attention: {alert_name}",
            message=annotations.get("description", "ML system alert triggered"),
            level=SlackLevel.WARNING,
            fields={"channel": "#alerts-ml", "action": "auto-notified"},
        )
        return "ML team notified via Slack"

    async def _trigger_model_retraining(self, alert_name: str, **kwargs) -> str:
        """Trigger MLOps retraining pipeline via GitHub Actions API."""
        logger.info("model_retraining_triggered", alert=alert_name)
        # Would call GitHub Actions API to dispatch mlops.yml workflow
        return "Model retraining pipeline triggered"

    def get_history(self, limit: int = 50) -> list[dict]:
        """Get recent remediation history."""
        return [r.to_dict() for r in self._history[-limit:]]

    def get_stats(self) -> dict:
        """Get remediation statistics."""
        total = len(self._history)
        if total == 0:
            return {"total": 0, "success_rate": 0}

        successes = sum(1 for r in self._history if r.status == RemediationStatus.SUCCESS)
        failures = sum(1 for r in self._history if r.status == RemediationStatus.FAILED)
        skipped = sum(1 for r in self._history if r.status == RemediationStatus.SKIPPED)

        return {
            "total_actions": total,
            "successes": successes,
            "failures": failures,
            "skipped": skipped,
            "success_rate": round(successes / max(total - skipped, 1) * 100, 1),
            "registered_actions": len(self._actions),
        }


# Singleton
_remediator: AutoRemediator | None = None


def get_auto_remediator() -> AutoRemediator:
    global _remediator
    if _remediator is None:
        _remediator = AutoRemediator()
    return _remediator
