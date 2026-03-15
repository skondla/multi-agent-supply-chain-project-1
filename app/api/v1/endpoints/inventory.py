"""
Inventory API endpoints.
"""
import math
import uuid
from typing import Optional
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models.inventory import Inventory
from app.schemas.inventory import (
    InventoryCreate, InventoryUpdate, InventoryAdjustment,
    InventoryResponse, InventoryListResponse, ReorderTriggerResponse,
)

logger = structlog.get_logger()
router = APIRouter()


@router.post("", response_model=InventoryResponse, status_code=status.HTTP_201_CREATED)
async def create_inventory_item(
    item_in: InventoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Add a new inventory item."""
    # Check SKU uniqueness
    existing = await db.execute(select(Inventory).where(Inventory.sku == item_in.sku))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"SKU '{item_in.sku}' already exists",
        )

    item = Inventory(**item_in.model_dump(), created_by=current_user_id)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("", response_model=InventoryListResponse)
async def list_inventory(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    warehouse_id: Optional[str] = None,
    search: Optional[str] = None,
    low_stock_only: bool = Query(False),
    is_active: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """List inventory items with filtering and pagination."""
    filters = [Inventory.is_active == is_active]
    if category:
        filters.append(Inventory.category == category)
    if warehouse_id:
        filters.append(Inventory.warehouse_id == warehouse_id)
    if search:
        filters.append(
            or_(Inventory.sku.ilike(f"%{search}%"), Inventory.product_name.ilike(f"%{search}%"))
        )
    if low_stock_only:
        filters.append(Inventory.quantity_on_hand <= Inventory.reorder_point)

    total_q = await db.execute(select(func.count(Inventory.id)).where(and_(*filters)))
    total = total_q.scalar()

    result = await db.execute(
        select(Inventory).where(and_(*filters))
        .order_by(Inventory.product_name)
        .offset((page - 1) * size).limit(size)
    )
    items = result.scalars().all()

    return InventoryListResponse(
        items=items, total=total, page=page, size=size,
        pages=math.ceil(total / size) if total else 0,
    )


@router.get("/low-stock", summary="Get items below reorder point")
async def get_low_stock_items(
    warehouse_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Get all inventory items that are at or below their reorder point."""
    filters = [
        Inventory.is_active == True,
        Inventory.quantity_on_hand <= Inventory.reorder_point,
    ]
    if warehouse_id:
        filters.append(Inventory.warehouse_id == warehouse_id)

    result = await db.execute(
        select(Inventory).where(and_(*filters)).order_by(Inventory.quantity_on_hand)
    )
    items = result.scalars().all()

    return {
        "count": len(items),
        "items": [
            {
                "sku": item.sku,
                "product_name": item.product_name,
                "quantity_on_hand": item.quantity_on_hand,
                "reorder_point": item.reorder_point,
                "reorder_quantity": item.reorder_quantity,
                "quantity_available": item.quantity_available,
                "estimated_reorder_cost": item.reorder_quantity * float(item.unit_cost),
                "warehouse_id": item.warehouse_id,
                "supplier_id": str(item.supplier_id) if item.supplier_id else None,
                "lead_time_days": item.lead_time_days,
            }
            for item in items
        ],
    }


@router.get("/{sku}", response_model=InventoryResponse)
async def get_inventory_item(
    sku: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Get inventory item by SKU."""
    result = await db.execute(select(Inventory).where(Inventory.sku == sku))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"SKU '{sku}' not found")
    return item


@router.put("/{sku}", response_model=InventoryResponse)
async def update_inventory_item(
    sku: str,
    update: InventoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Update inventory item properties."""
    result = await db.execute(select(Inventory).where(Inventory.sku == sku))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"SKU '{sku}' not found")

    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    item.updated_by = current_user_id

    await db.commit()
    await db.refresh(item)
    return item


@router.post("/{sku}/adjust", response_model=InventoryResponse)
async def adjust_inventory(
    sku: str,
    adjustment: InventoryAdjustment,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Adjust inventory quantity (positive to add, negative to remove)."""
    result = await db.execute(select(Inventory).where(Inventory.sku == sku))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"SKU '{sku}' not found")

    new_qty = item.quantity_on_hand + adjustment.quantity_delta
    if new_qty < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Adjustment would result in negative quantity ({new_qty})",
        )

    item.quantity_on_hand = new_qty
    item.updated_by = current_user_id
    await db.commit()
    await db.refresh(item)

    logger.info(
        "Inventory adjusted",
        sku=sku, delta=adjustment.quantity_delta,
        new_qty=new_qty, reason=adjustment.reason,
    )
    return item


@router.post("/reorder", response_model=ReorderTriggerResponse, summary="Trigger AI-powered reordering")
async def trigger_reorder(
    background_tasks: BackgroundTasks,
    warehouse_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Trigger automatic reorder for all low-stock items using AI recommendations."""
    filters = [
        Inventory.is_active == True,
        Inventory.quantity_on_hand <= Inventory.reorder_point,
    ]
    if warehouse_id:
        filters.append(Inventory.warehouse_id == warehouse_id)

    result = await db.execute(select(Inventory).where(and_(*filters)))
    low_stock_items = result.scalars().all()

    reorders = []
    total_cost = 0.0
    for item in low_stock_items:
        cost = float(item.reorder_quantity) * float(item.unit_cost)
        total_cost += cost
        reorders.append({
            "sku": item.sku,
            "product_name": item.product_name,
            "current_qty": item.quantity_on_hand,
            "reorder_qty": item.reorder_quantity,
            "estimated_cost": cost,
            "supplier_id": str(item.supplier_id) if item.supplier_id else None,
        })

    return ReorderTriggerResponse(
        items_assessed=len(low_stock_items),
        reorders_triggered=reorders,
        total_reorder_cost_estimate=round(total_cost, 2),
    )
