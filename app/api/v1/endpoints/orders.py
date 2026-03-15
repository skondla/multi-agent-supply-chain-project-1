"""
Orders API endpoints - CRUD and agent-powered processing.
"""
import math
import uuid
from datetime import datetime
from typing import Optional
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.core.kafka_client import publish_order_event
from app.models.order import Order, OrderStatus, OrderPriority
from app.schemas.order import (
    OrderCreate, OrderUpdate, OrderResponse, OrderListResponse,
    OrderProcessResponse, BulkOrderCreate,
)

logger = structlog.get_logger()
router = APIRouter()


def _generate_order_number() -> str:
    """Generate a unique order number."""
    now = datetime.utcnow()
    suffix = str(uuid.uuid4())[:8].upper()
    return f"ORD-{now.strftime('%Y%m')}-{suffix}"


def _calculate_totals(items: list) -> dict:
    """Calculate order financial totals."""
    subtotal = sum(
        float(item["quantity"]) * float(item["unit_price"]) for item in items
    )
    tax = subtotal * 0.08  # 8% default tax
    shipping = 0.0 if subtotal >= 100 else 15.0
    return {
        "subtotal": round(subtotal, 2),
        "tax_amount": round(tax, 2),
        "shipping_cost": shipping,
        "discount_amount": 0.0,
        "total_amount": round(subtotal + tax + shipping, 2),
    }


async def _trigger_agent_processing(order_id: str, order_data: dict, db: AsyncSession):
    """Background task: trigger multi-agent order processing."""
    from agents.orchestrator_agent import OrchestratorAgent

    try:
        orchestrator = OrchestratorAgent()
        result = await orchestrator.process({
            "task_type": "order_processing",
            "data": {"order_id": order_id, **order_data},
            "priority": order_data.get("priority", "medium"),
        })
        # Update order with agent task ID
        order = await db.get(Order, uuid.UUID(order_id))
        if order:
            order.agent_task_id = result.get("task_id")
            order.status = OrderStatus.CONFIRMED
            await db.commit()
    except Exception as e:
        logger.error("Agent processing failed", order_id=order_id, error=str(e))


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED,
             summary="Create a new order")
async def create_order(
    order_in: OrderCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Create a new supply chain order.

    The order will be automatically processed by AI agents that will:
    - Validate inventory availability
    - Check fraud indicators
    - Select optimal supplier and carrier
    - Calculate accurate pricing
    """
    items_dict = [item.model_dump() for item in order_in.items]
    # Add total to each item
    for item in items_dict:
        item["total_price"] = round(float(item["quantity"]) * float(item["unit_price"]), 2)

    totals = _calculate_totals(items_dict)

    order = Order(
        order_number=_generate_order_number(),
        status=OrderStatus.PENDING,
        priority=order_in.priority,
        customer_id=order_in.customer_id,
        customer_name=order_in.customer_name,
        customer_email=str(order_in.customer_email) if order_in.customer_email else None,
        items=items_dict,
        shipping_address=order_in.shipping_address.model_dump(),
        billing_address=order_in.billing_address.model_dump() if order_in.billing_address else None,
        notes=order_in.notes,
        tags=order_in.tags or [],
        metadata=order_in.metadata or {},
        created_by=current_user_id,
        **totals,
    )

    db.add(order)
    await db.commit()
    await db.refresh(order)

    # Publish Kafka event
    await publish_order_event(
        str(order.id), "order_created",
        {"order_number": order.order_number, "total": float(order.total_amount)},
    )

    # Trigger agent processing asynchronously
    background_tasks.add_task(
        _trigger_agent_processing,
        str(order.id),
        {"priority": order.priority, "items": items_dict, "customer_id": order.customer_id},
        db,
    )

    logger.info("Order created", order_id=str(order.id), order_number=order.order_number)
    return order


@router.get("", response_model=OrderListResponse, summary="List orders with filtering")
async def list_orders(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[OrderStatus] = None,
    priority: Optional[OrderPriority] = None,
    customer_id: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """List orders with pagination, filtering, and search."""
    filters = []
    if status:
        filters.append(Order.status == status)
    if priority:
        filters.append(Order.priority == priority)
    if customer_id:
        filters.append(Order.customer_id == customer_id)
    if search:
        filters.append(
            or_(
                Order.order_number.ilike(f"%{search}%"),
                Order.customer_id.ilike(f"%{search}%"),
            )
        )

    total_q = await db.execute(
        select(func.count(Order.id)).where(and_(*filters) if filters else True)
    )
    total = total_q.scalar()

    result = await db.execute(
        select(Order)
        .where(and_(*filters) if filters else True)
        .order_by(Order.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    orders = result.scalars().all()

    return OrderListResponse(
        items=orders,
        total=total,
        page=page,
        size=size,
        pages=math.ceil(total / size) if total else 0,
    )


@router.get("/{order_id}", response_model=OrderResponse, summary="Get order by ID")
async def get_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Get a specific order by its UUID."""
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


@router.put("/{order_id}", response_model=OrderResponse, summary="Update order")
async def update_order(
    order_id: uuid.UUID,
    order_update: OrderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Update an order's status, priority, or metadata."""
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    update_data = order_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(order, field, value)
    order.updated_by = current_user_id

    await db.commit()
    await db.refresh(order)
    return order


@router.delete("/{order_id}", response_model=OrderResponse, summary="Cancel order")
async def cancel_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Cancel a pending or confirmed order."""
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if not order.is_cancellable:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order in status '{order.status}' cannot be cancelled",
        )

    order.status = OrderStatus.CANCELLED
    order.updated_by = current_user_id
    await db.commit()
    await db.refresh(order)

    await publish_order_event(str(order.id), "order_cancelled", {"reason": "user_request"})
    return order


@router.post("/{order_id}/process", response_model=OrderProcessResponse,
             status_code=status.HTTP_202_ACCEPTED, summary="Trigger AI agent processing")
async def process_order(
    order_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Trigger multi-agent AI processing for an order.

    This invokes the orchestrator which will coordinate inventory, supplier,
    logistics, and fraud detection agents.
    """
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    task_id = str(uuid.uuid4())

    background_tasks.add_task(
        _trigger_agent_processing,
        str(order.id),
        {
            "priority": str(order.priority),
            "items": order.items,
            "customer_id": order.customer_id,
            "total_amount": float(order.total_amount),
        },
        db,
    )

    return OrderProcessResponse(
        order_id=str(order_id),
        task_id=task_id,
        message="Order processing triggered. Agents are analyzing the order.",
        estimated_completion_seconds=30,
    )


@router.get("/{order_id}/status", summary="Get real-time order status")
async def get_order_status(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Get real-time status of an order including agent processing state."""
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    return {
        "order_id": str(order.id),
        "order_number": order.order_number,
        "status": order.status,
        "priority": order.priority,
        "agent_task_id": order.agent_task_id,
        "tracking_number": order.tracking_number,
        "estimated_delivery": order.estimated_delivery,
        "updated_at": order.updated_at,
    }


@router.post("/bulk", status_code=status.HTTP_202_ACCEPTED, summary="Bulk order creation")
async def bulk_create_orders(
    bulk_request: BulkOrderCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Create multiple orders in a single request (max 100)."""
    order_ids = []
    for order_in in bulk_request.orders:
        items_dict = [item.model_dump() for item in order_in.items]
        for item in items_dict:
            item["total_price"] = round(float(item["quantity"]) * float(item["unit_price"]), 2)
        totals = _calculate_totals(items_dict)

        order = Order(
            order_number=_generate_order_number(),
            status=OrderStatus.PENDING,
            priority=order_in.priority,
            customer_id=order_in.customer_id,
            items=items_dict,
            shipping_address=order_in.shipping_address.model_dump(),
            created_by=current_user_id,
            **totals,
        )
        db.add(order)
        order_ids.append(str(order.id))

    await db.commit()
    return {
        "created": len(order_ids),
        "order_ids": order_ids,
        "message": "Bulk orders created. Processing will begin shortly.",
    }
