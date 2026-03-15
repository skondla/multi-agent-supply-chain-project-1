"""
Shipments API endpoints - tracking and logistics management.
"""
import math
import uuid
from typing import Optional
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models.shipment import Shipment, ShipmentStatus

logger = structlog.get_logger()
router = APIRouter()


@router.get("", summary="List shipments")
async def list_shipments(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[ShipmentStatus] = None,
    order_id: Optional[uuid.UUID] = None,
    carrier: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    filters = []
    if status:
        filters.append(Shipment.status == status)
    if order_id:
        filters.append(Shipment.order_id == order_id)
    if carrier:
        filters.append(Shipment.carrier == carrier)

    total_q = await db.execute(
        select(func.count(Shipment.id)).where(and_(*filters) if filters else True)
    )
    total = total_q.scalar()

    result = await db.execute(
        select(Shipment).where(and_(*filters) if filters else True)
        .order_by(Shipment.created_at.desc())
        .offset((page - 1) * size).limit(size)
    )
    shipments = result.scalars().all()

    return {
        "items": [
            {
                "id": str(s.id),
                "tracking_number": s.tracking_number,
                "status": s.status,
                "carrier": s.carrier,
                "order_id": str(s.order_id),
                "estimated_arrival": s.estimated_arrival,
                "actual_arrival": s.actual_arrival,
                "current_location": s.current_location,
                "created_at": s.created_at,
            }
            for s in shipments
        ],
        "total": total,
        "page": page,
        "size": size,
        "pages": math.ceil(total / size) if total else 0,
    }


@router.get("/{shipment_id}", summary="Get shipment details")
async def get_shipment(
    shipment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    shipment = await db.get(Shipment, shipment_id)
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return shipment


@router.get("/track/{tracking_number}", summary="Track shipment by tracking number")
async def track_shipment(
    tracking_number: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Get real-time tracking info for a shipment."""
    result = await db.execute(
        select(Shipment).where(Shipment.tracking_number == tracking_number)
    )
    shipment = result.scalar_one_or_none()
    if not shipment:
        raise HTTPException(status_code=404, detail=f"Tracking number '{tracking_number}' not found")

    # In production: call carrier API for live tracking
    return {
        "tracking_number": tracking_number,
        "carrier": shipment.carrier,
        "status": shipment.status,
        "current_location": shipment.current_location,
        "estimated_arrival": shipment.estimated_arrival,
        "actual_arrival": shipment.actual_arrival,
        "route_history": shipment.route_history or [],
        "is_delayed": shipment.is_delayed == "true",
        "delay_reason": shipment.delay_reason,
        "last_update": shipment.last_update,
    }
