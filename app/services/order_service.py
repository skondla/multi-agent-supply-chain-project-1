"""Order business logic service."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderStatus, OrderPriority
from app.schemas.order import OrderCreate, OrderUpdate

logger = structlog.get_logger(__name__)


class OrderService:
    """Service layer for order operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_order(self, data: OrderCreate, created_by_id: str | None = None) -> Order:
        """Create a new order with auto-generated order number."""
        order_number = f"ORD-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

        order = Order(
            order_number=order_number,
            customer_id=data.customer_id,
            customer_email=data.customer_email,
            customer_name=data.customer_name,
            status=OrderStatus.PENDING,
            priority=OrderPriority(data.priority) if data.priority else OrderPriority.STANDARD,
            items=[item.model_dump() for item in data.items],
            shipping_address=data.shipping_address.model_dump() if data.shipping_address else None,
            billing_address=data.billing_address.model_dump() if data.billing_address else None,
            notes=data.notes,
            requested_delivery_date=data.requested_delivery_date,
            currency=data.currency or "USD",
        )

        # Calculate totals
        subtotal = sum(
            float(item.unit_price) * item.quantity for item in data.items
        )
        order.subtotal = subtotal
        order.tax_amount = round(subtotal * 0.08, 2)  # 8% tax
        order.shipping_cost = self._calculate_shipping_cost(data)
        order.total_amount = order.subtotal + order.tax_amount + order.shipping_cost

        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)

        logger.info("order_created", order_id=str(order.id), order_number=order_number)
        return order

    async def get_order(self, order_id: str) -> Order | None:
        """Get order by ID."""
        result = await self.db.execute(
            select(Order).where(Order.id == order_id)
        )
        return result.scalar_one_or_none()

    async def get_order_by_number(self, order_number: str) -> Order | None:
        """Get order by order number."""
        result = await self.db.execute(
            select(Order).where(Order.order_number == order_number)
        )
        return result.scalar_one_or_none()

    async def list_orders(
        self,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        customer_id: str | None = None,
        search: str | None = None,
    ) -> tuple[list[Order], int]:
        """List orders with pagination and filtering."""
        query = select(Order)
        count_query = select(func.count(Order.id))

        if status:
            query = query.where(Order.status == status)
            count_query = count_query.where(Order.status == status)

        if customer_id:
            query = query.where(Order.customer_id == customer_id)
            count_query = count_query.where(Order.customer_id == customer_id)

        if search:
            search_filter = or_(
                Order.customer_name.ilike(f"%{search}%"),
                Order.customer_email.ilike(f"%{search}%"),
                Order.order_number.ilike(f"%{search}%"),
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(Order.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        orders = result.scalars().all()

        return list(orders), total

    async def update_order(self, order_id: str, data: OrderUpdate) -> Order | None:
        """Update an existing order."""
        order = await self.get_order(order_id)
        if not order:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(order, field, value)

        order.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def cancel_order(self, order_id: str, reason: str | None = None) -> Order | None:
        """Cancel an order if it's in a cancellable state."""
        order = await self.get_order(order_id)
        if not order or not order.is_cancellable:
            return None

        order.status = OrderStatus.CANCELLED
        order.cancelled_at = datetime.now(timezone.utc)
        order.updated_at = datetime.now(timezone.utc)
        if reason:
            order.notes = f"{order.notes or ''}\nCancellation reason: {reason}".strip()

        await self.db.commit()
        await self.db.refresh(order)
        logger.info("order_cancelled", order_id=order_id)
        return order

    def _calculate_shipping_cost(self, data: OrderCreate) -> float:
        """Calculate shipping cost based on order items and destination."""
        total_items = sum(item.quantity for item in data.items)
        base_cost = 5.99
        per_item_cost = 0.50
        return round(base_cost + (per_item_cost * total_items), 2)
