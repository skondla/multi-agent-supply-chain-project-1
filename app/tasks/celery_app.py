"""Celery application configuration for supply chain background tasks."""
from celery import Celery
from kombu import Exchange, Queue

from app.core.config import settings

# ── Celery App ────────────────────────────────────────────────────────────────
celery_app = Celery(
    "supply_chain",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.supply_chain_tasks",
    ],
)

# ── Configuration ─────────────────────────────────────────────────────────────
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Result backend
    result_expires=3600,  # 1 hour
    result_backend_transport_options={
        "retry_policy": {"timeout": 5.0},
    },
    # Task routing
    task_default_queue="default",
    task_queues=(
        Queue("default", Exchange("default"), routing_key="default"),
        Queue("orders", Exchange("orders"), routing_key="orders"),
        Queue("inventory", Exchange("inventory"), routing_key="inventory"),
        Queue("ml", Exchange("ml"), routing_key="ml"),
        Queue("alerts", Exchange("alerts"), routing_key="alerts"),
    ),
    task_routes={
        "app.tasks.supply_chain_tasks.process_order": {"queue": "orders"},
        "app.tasks.supply_chain_tasks.check_inventory_levels": {"queue": "inventory"},
        "app.tasks.supply_chain_tasks.run_demand_forecast": {"queue": "ml"},
        "app.tasks.supply_chain_tasks.detect_anomalies": {"queue": "ml"},
        "app.tasks.supply_chain_tasks.send_alert": {"queue": "alerts"},
        "app.tasks.supply_chain_tasks.generate_reorder_recommendations": {"queue": "inventory"},
        "app.tasks.supply_chain_tasks.update_supplier_scores": {"queue": "default"},
    },
    # Worker settings
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Retry settings
    task_max_retries=3,
    task_default_retry_delay=60,
    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
    # Beat schedule (periodic tasks)
    beat_schedule={
        "check-inventory-every-15min": {
            "task": "app.tasks.supply_chain_tasks.check_inventory_levels",
            "schedule": 900.0,  # 15 minutes
            "options": {"queue": "inventory"},
        },
        "run-demand-forecast-daily": {
            "task": "app.tasks.supply_chain_tasks.run_demand_forecast",
            "schedule": 86400.0,  # 24 hours
            "options": {"queue": "ml"},
        },
        "detect-anomalies-hourly": {
            "task": "app.tasks.supply_chain_tasks.detect_anomalies",
            "schedule": 3600.0,  # 1 hour
            "options": {"queue": "ml"},
        },
        "update-supplier-scores-daily": {
            "task": "app.tasks.supply_chain_tasks.update_supplier_scores",
            "schedule": 86400.0,
            "options": {"queue": "default"},
        },
        "generate-reorder-recommendations-hourly": {
            "task": "app.tasks.supply_chain_tasks.generate_reorder_recommendations",
            "schedule": 3600.0,
            "options": {"queue": "inventory"},
        },
    },
)
