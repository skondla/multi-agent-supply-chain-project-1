"""
Pydantic v2 schemas for Order API endpoints.
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, model_validator, EmailStr

from app.models.order import OrderStatus, OrderPriority


class AddressSchema(BaseModel):
    street: str = Field(..., min_length=1, max_length=500)
    city: str = Field(..., min_length=1, max_length=200)
    state: str = Field(..., min_length=1, max_length=100)
    zip: str = Field(..., min_length=1, max_length=20)
    country: str = Field(..., min_length=2, max_length=100)
    street2: Optional[str] = None


class OrderItemCreate(BaseModel):
    sku: str = Field(..., min_length=1, max_length=100)
    quantity: int = Field(..., gt=0, le=10000)
    unit_price: Decimal = Field(..., gt=0, decimal_places=2)
    notes: Optional[str] = None


class OrderItemResponse(OrderItemCreate):
    total_price: Decimal

    model_config = {"from_attributes": True}


class OrderCreate(BaseModel):
    customer_id: str = Field(..., min_length=1, max_length=100)
    customer_name: Optional[str] = None
    customer_email: Optional[EmailStr] = None
    items: List[OrderItemCreate] = Field(..., min_length=1)
    shipping_address: AddressSchema
    billing_address: Optional[AddressSchema] = None
    priority: OrderPriority = OrderPriority.MEDIUM
    notes: Optional[str] = None
    tags: Optional[List[str]] = []
    metadata: Optional[Dict[str, Any]] = {}

    @model_validator(mode="after")
    def validate_items(self) -> "OrderCreate":
        if not self.items:
            raise ValueError("Order must have at least one item")
        return self


class OrderUpdate(BaseModel):
    status: Optional[OrderStatus] = None
    priority: Optional[OrderPriority] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    estimated_delivery: Optional[datetime] = None
    tracking_number: Optional[str] = None


class OrderResponse(BaseModel):
    id: UUID
    order_number: str
    status: OrderStatus
    priority: OrderPriority
    customer_id: str
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    items: List[Dict[str, Any]]
    shipping_address: Dict[str, Any]
    billing_address: Optional[Dict[str, Any]] = None
    subtotal: Decimal
    tax_amount: Decimal
    shipping_cost: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    currency: str
    supplier_id: Optional[UUID] = None
    warehouse_id: Optional[str] = None
    tracking_number: Optional[str] = None
    estimated_delivery: Optional[datetime] = None
    actual_delivery: Optional[datetime] = None
    shipped_at: Optional[datetime] = None
    agent_task_id: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = []
    is_fraud_flagged: bool = False
    fraud_score: Optional[Decimal] = None
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    items: List[OrderResponse]
    total: int
    page: int
    size: int
    pages: int


class OrderProcessResponse(BaseModel):
    order_id: str
    task_id: str
    message: str
    estimated_completion_seconds: int = 30


class BulkOrderCreate(BaseModel):
    orders: List[OrderCreate] = Field(..., min_length=1, max_length=100)
