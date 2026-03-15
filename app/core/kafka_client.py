"""
Kafka producer/consumer using aiokafka with connection management.
"""
import json
from typing import Any, Callable, Optional
import structlog
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError

from app.core.config import settings

logger = structlog.get_logger()

_producer: Optional[AIOKafkaProducer] = None


async def init_kafka() -> None:
    """Initialize Kafka producer."""
    global _producer
    try:
        _producer = AIOKafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            acks="all",
            enable_idempotence=True,
            compression_type="gzip",
            max_batch_size=32768,
            linger_ms=5,
        )
        await _producer.start()
        logger.info("Kafka producer started", servers=settings.KAFKA_BOOTSTRAP_SERVERS)
    except KafkaConnectionError as e:
        logger.warning("Kafka not available, running without event streaming", error=str(e))
        _producer = None


async def close_kafka() -> None:
    """Stop Kafka producer."""
    global _producer
    if _producer:
        await _producer.stop()
        _producer = None
        logger.info("Kafka producer stopped")


def get_producer() -> Optional[AIOKafkaProducer]:
    return _producer


async def publish_event(topic: str, event: dict, key: Optional[str] = None) -> bool:
    """Publish an event to Kafka topic."""
    producer = get_producer()
    if producer is None:
        logger.warning("Kafka not available, event not published", topic=topic)
        return False
    try:
        await producer.send_and_wait(topic, value=event, key=key)
        logger.debug("Event published", topic=topic, key=key)
        return True
    except Exception as e:
        logger.error("Failed to publish event", topic=topic, error=str(e))
        return False


async def publish_order_event(order_id: str, event_type: str, data: dict) -> bool:
    """Publish an order event."""
    event = {
        "event_type": event_type,
        "order_id": order_id,
        "timestamp": str(__import__("datetime").datetime.utcnow().isoformat()),
        "data": data,
    }
    return await publish_event(settings.KAFKA_TOPIC_ORDERS, event, key=order_id)


async def publish_inventory_event(sku: str, event_type: str, data: dict) -> bool:
    """Publish an inventory event."""
    event = {
        "event_type": event_type,
        "sku": sku,
        "timestamp": str(__import__("datetime").datetime.utcnow().isoformat()),
        "data": data,
    }
    return await publish_event(settings.KAFKA_TOPIC_INVENTORY, event, key=sku)


async def publish_alert(alert_type: str, severity: str, data: dict) -> bool:
    """Publish a supply chain alert."""
    event = {
        "alert_type": alert_type,
        "severity": severity,
        "timestamp": str(__import__("datetime").datetime.utcnow().isoformat()),
        "data": data,
    }
    return await publish_event(settings.KAFKA_TOPIC_ALERTS, event, key=alert_type)


async def check_kafka_health() -> bool:
    """Check Kafka connectivity."""
    producer = get_producer()
    return producer is not None
