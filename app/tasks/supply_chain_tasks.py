"""Supply chain background tasks executed by Celery workers."""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from celery import Task

from app.tasks.celery_app import celery_app

logger = structlog.get_logger(__name__)


def run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class BaseSupplyChainTask(Task):
    """Base Celery task with common error handling and logging."""

    abstract = True
    max_retries = 3
    default_retry_delay = 60

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(
            "task_failed",
            task_id=task_id,
            task_name=self.name,
            error=str(exc),
            args=args,
        )
        # Send Slack alert for task failures
        send_alert.delay(
            level="warning",
            title=f"Celery Task Failed: {self.name}",
            message=f"Task {task_id} failed with error: {exc}",
        )

    def on_success(self, retval, task_id, args, kwargs):
        logger.info(
            "task_succeeded",
            task_id=task_id,
            task_name=self.name,
        )


@celery_app.task(
    bind=True,
    base=BaseSupplyChainTask,
    name="app.tasks.supply_chain_tasks.process_order",
    queue="orders",
)
def process_order(self, order_id: str, priority: str = "standard") -> dict[str, Any]:
    """Process an order through the multi-agent orchestration pipeline."""
    async def _process():
        from app.core.database import AsyncSessionLocal
        from app.models.order import Order, OrderStatus
        from agents.orchestrator_agent import OrchestratorAgent
        from app.core.config import settings

        logger.info("processing_order", order_id=order_id, priority=priority)

        async with AsyncSessionLocal() as db:
            # Get order
            from sqlalchemy import select
            result = await db.execute(select(Order).where(Order.id == order_id))
            order = result.scalar_one_or_none()

            if not order:
                logger.error("order_not_found", order_id=order_id)
                return {"status": "error", "message": "Order not found"}

            # Update status to processing
            order.status = OrderStatus.PROCESSING
            order.updated_at = datetime.now(timezone.utc)
            await db.commit()

            # Run orchestrator agent
            agent = OrchestratorAgent(settings.anthropic_api_key)
            result = await agent.process({
                "task": "process_order",
                "order_id": order_id,
                "priority": priority,
                "order_data": {
                    "customer_id": str(order.customer_id),
                    "items": order.items,
                    "total_amount": float(order.total_amount or 0),
                    "priority": order.priority.value if order.priority else "standard",
                },
            })

            return {"status": "success", "order_id": order_id, "result": result}

    try:
        return run_async(_process())
    except Exception as exc:
        logger.error("order_processing_failed", order_id=order_id, error=str(exc))
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(
    bind=True,
    base=BaseSupplyChainTask,
    name="app.tasks.supply_chain_tasks.check_inventory_levels",
    queue="inventory",
)
def check_inventory_levels(self) -> dict[str, Any]:
    """Check inventory levels and trigger reorder recommendations."""
    async def _check():
        from app.core.database import AsyncSessionLocal
        from app.models.inventory import Inventory
        from sqlalchemy import select
        from agents.inventory_agent import InventoryAgent
        from app.core.config import settings

        logger.info("checking_inventory_levels")

        async with AsyncSessionLocal() as db:
            # Get all low stock items
            result = await db.execute(
                select(Inventory).where(Inventory.quantity_on_hand <= Inventory.reorder_point)
            )
            low_stock_items = result.scalars().all()

            if not low_stock_items:
                logger.info("no_low_stock_items")
                return {"status": "ok", "low_stock_count": 0}

            logger.warning("low_stock_detected", count=len(low_stock_items))

            # Trigger reorder recommendations
            generate_reorder_recommendations.delay(
                sku_list=[item.sku for item in low_stock_items]
            )

            return {
                "status": "ok",
                "low_stock_count": len(low_stock_items),
                "skus": [item.sku for item in low_stock_items],
            }

    return run_async(_check())


@celery_app.task(
    bind=True,
    base=BaseSupplyChainTask,
    name="app.tasks.supply_chain_tasks.generate_reorder_recommendations",
    queue="inventory",
)
def generate_reorder_recommendations(self, sku_list: list[str] | None = None) -> dict[str, Any]:
    """Generate AI-powered reorder recommendations for low-stock items."""
    async def _generate():
        from agents.inventory_agent import InventoryAgent
        from app.core.config import settings

        logger.info("generating_reorder_recommendations", sku_count=len(sku_list or []))

        agent = InventoryAgent(settings.anthropic_api_key)
        recommendations = []

        for sku in (sku_list or []):
            try:
                rec = await agent.generate_reorder_recommendation(sku)
                recommendations.append(rec)
            except Exception as e:
                logger.error("reorder_recommendation_failed", sku=sku, error=str(e))

        if recommendations:
            send_alert.delay(
                level="info",
                title=f"Reorder Recommendations Generated",
                message=f"Generated {len(recommendations)} reorder recommendations for low-stock items.",
                metadata={"recommendations": recommendations[:5]},  # First 5
            )

        return {"status": "ok", "recommendation_count": len(recommendations)}

    try:
        return run_async(_generate())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=120)


@celery_app.task(
    bind=True,
    base=BaseSupplyChainTask,
    name="app.tasks.supply_chain_tasks.run_demand_forecast",
    queue="ml",
)
def run_demand_forecast(self, product_ids: list[str] | None = None) -> dict[str, Any]:
    """Run demand forecasting for all or specified products."""
    async def _forecast():
        from agents.demand_forecast_agent import DemandForecastAgent
        from app.core.config import settings

        logger.info("running_demand_forecast")

        agent = DemandForecastAgent(settings.anthropic_api_key)
        result = await agent.process({
            "task": "generate_forecasts",
            "product_ids": product_ids,
            "horizon_days": 30,
        })

        return {"status": "ok", "forecast_result": result}

    try:
        return run_async(_forecast())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=300)


@celery_app.task(
    bind=True,
    base=BaseSupplyChainTask,
    name="app.tasks.supply_chain_tasks.detect_anomalies",
    queue="ml",
)
def detect_anomalies(self) -> dict[str, Any]:
    """Run anomaly detection across orders and inventory."""
    async def _detect():
        from agents.anomaly_detection_agent import AnomalyDetectionAgent
        from app.core.config import settings
        from app.core.database import AsyncSessionLocal
        from app.models.order import Order, OrderStatus
        from sqlalchemy import select
        from datetime import timedelta

        logger.info("running_anomaly_detection")

        async with AsyncSessionLocal() as db:
            # Get recent orders for anomaly scanning
            cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
            result = await db.execute(
                select(Order)
                .where(Order.created_at >= cutoff)
                .limit(1000)
            )
            recent_orders = result.scalars().all()

        agent = AnomalyDetectionAgent(settings.anthropic_api_key)
        anomaly_result = await agent.process({
            "task": "detect_anomalies",
            "order_ids": [str(o.id) for o in recent_orders],
            "time_window_hours": 1,
        })

        return {"status": "ok", "anomalies_scanned": len(recent_orders), "result": anomaly_result}

    try:
        return run_async(_detect())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(
    bind=True,
    base=BaseSupplyChainTask,
    name="app.tasks.supply_chain_tasks.update_supplier_scores",
    queue="default",
)
def update_supplier_scores(self) -> dict[str, Any]:
    """Recalculate supplier performance scores."""
    async def _update():
        from app.core.database import AsyncSessionLocal
        from app.models.supplier import Supplier
        from sqlalchemy import select

        logger.info("updating_supplier_scores")

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Supplier).where(Supplier.is_active == True))
            suppliers = result.scalars().all()

            updated = 0
            for supplier in suppliers:
                # Recompute overall score as weighted average
                supplier.overall_score = (
                    supplier.reliability_score * 0.30
                    + supplier.quality_score * 0.25
                    + supplier.delivery_score * 0.25
                    + supplier.price_competitiveness_score * 0.20
                )
                supplier.updated_at = datetime.now(timezone.utc)
                updated += 1

            await db.commit()
            logger.info("supplier_scores_updated", count=updated)
            return {"status": "ok", "updated_count": updated}

    return run_async(_update())


@celery_app.task(
    bind=True,
    base=BaseSupplyChainTask,
    name="app.tasks.supply_chain_tasks.send_alert",
    queue="alerts",
    max_retries=5,
)
def send_alert(
    self,
    level: str,
    title: str,
    message: str,
    metadata: dict | None = None,
) -> dict[str, Any]:
    """Send an alert via Slack."""
    async def _send():
        from app.core.slack_notifier import SlackNotifier, SlackLevel
        from app.core.config import settings

        level_map = {
            "info": SlackLevel.INFO,
            "warning": SlackLevel.WARNING,
            "error": SlackLevel.ERROR,
            "critical": SlackLevel.CRITICAL,
        }

        notifier = SlackNotifier(settings.slack_webhook_url)
        await notifier.send_alert(
            title=title,
            message=message,
            level=level_map.get(level, SlackLevel.INFO),
            fields=metadata or {},
        )
        return {"status": "sent"}

    try:
        return run_async(_send())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)
