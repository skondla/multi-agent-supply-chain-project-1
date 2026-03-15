"""
Pydantic v2 schemas for Inventory API endpoints.
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, model_validator


class InventoryCreate(BaseModel):
    sku: str = Field(..., min_length=1, max_length=100)
    product_name: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    barcode: Optional[str] = None
    quantity_on_hand: int = Field(0, ge=0)
    reorder_point: int = Field(10, ge=0)
    reorder_quantity: int = Field(50, ge=1)
    max_quantity: Optional[int] = Field(None, ge=0)
    unit_cost: Decimal = Field(0, ge=0, decimal_places=4)
    unit_price: Decimal = Field(0, ge=0, decimal_places=4)
    currency: str = "USD"
    warehouse_id: Optional[str] = None
    aisle: Optional[str] = None
    shelf: Optional[str] = None
    bin_number: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    tags: Optional[List[str]] = []
    supplier_id: Optional[UUID] = None
    lead_time_days: int = Field(7, ge=0)
    supplier_sku: Optional[str] = None
    is_perishable: bool = False
    is_hazardous: bool = False
    attributes: Optional[Dict[str, Any]] = {}


class InventoryUpdate(BaseModel):
    product_name: Optional[str] = None
    description: Optional[str] = None
    reorder_point: Optional[int] = Field(None, ge=0)
    reorder_quantity: Optional[int] = Field(None, ge=1)
    max_quantity: Optional[int] = Field(None, ge=0)
    unit_cost: Optional[Decimal] = Field(None, ge=0)
    unit_price: Optional[Decimal] = Field(None, ge=0)
    warehouse_id: Optional[str] = None
    aisle: Optional[str] = None
    shelf: Optional[str] = None
    category: Optional[str] = None
    supplier_id: Optional[UUID] = None
    lead_time_days: Optional[int] = None
    is_active: Optional[bool] = None
    tags: Optional[List[str]] = None
    attributes: Optional[Dict[str, Any]] = None


class InventoryAdjustment(BaseModel):
    quantity_delta: int = Field(..., description="Positive to add, negative to remove")
    reason: str = Field(..., min_length=1, max_length=500)
    reference: Optional[str] = None  # PO number, return ID, etc.

    @model_validator(mode="after")
    def validate_reason(self) -> "InventoryAdjustment":
        if self.quantity_delta == 0:
            raise ValueError("Quantity delta cannot be zero")
        return self


class InventoryResponse(BaseModel):
    id: UUID
    sku: str
    product_name: str
    description: Optional[str] = None
    quantity_on_hand: int
    quantity_reserved: int
    quantity_available: int
    quantity_in_transit: int
    reorder_point: int
    reorder_quantity: int
    max_quantity: Optional[int] = None
    unit_cost: Decimal
    unit_price: Decimal
    currency: str
    warehouse_id: Optional[str] = None
    aisle: Optional[str] = None
    shelf: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    tags: List[str] = []
    supplier_id: Optional[UUID] = None
    lead_time_days: int
    is_active: bool
    is_perishable: bool
    is_hazardous: bool
    is_low_stock: bool
    is_out_of_stock: bool
    needs_reorder: bool
    total_value: float
    demand_forecast_7d: Optional[Decimal] = None
    demand_forecast_30d: Optional[Decimal] = None
    last_counted_at: Optional[datetime] = None
    last_restocked_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InventoryListResponse(BaseModel):
    items: List[InventoryResponse]
    total: int
    page: int
    size: int
    pages: int


class ReorderTriggerResponse(BaseModel):
    items_assessed: int
    reorders_triggered: List[Dict[str, Any]]
    total_reorder_cost_estimate: float
