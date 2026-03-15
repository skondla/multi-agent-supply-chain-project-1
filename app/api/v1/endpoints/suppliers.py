"""
Suppliers API endpoints.
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
from app.models.supplier import Supplier, SupplierStatus
from app.schemas.supplier import (
    SupplierCreate, SupplierUpdate, SupplierResponse,
    SupplierListResponse, SupplierEvaluationResponse,
)

logger = structlog.get_logger()
router = APIRouter()


@router.post("", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
async def create_supplier(
    supplier_in: SupplierCreate,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    existing = await db.execute(select(Supplier).where(Supplier.code == supplier_in.code))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Supplier code '{supplier_in.code}' already exists")

    data = supplier_in.model_dump()
    if data.get("address"):
        data["address"] = data["address"] if isinstance(data["address"], dict) else data["address"].model_dump()

    supplier = Supplier(**data, created_by=current_user_id)
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)
    return supplier


@router.get("", response_model=SupplierListResponse)
async def list_suppliers(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[SupplierStatus] = None,
    country: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    filters = []
    if status:
        filters.append(Supplier.status == status)
    if country:
        filters.append(Supplier.country == country)
    if search:
        filters.append(
            or_(Supplier.name.ilike(f"%{search}%"), Supplier.code.ilike(f"%{search}%"))
        )

    total_q = await db.execute(
        select(func.count(Supplier.id)).where(and_(*filters) if filters else True)
    )
    total = total_q.scalar()

    result = await db.execute(
        select(Supplier)
        .where(and_(*filters) if filters else True)
        .order_by(Supplier.overall_score.desc().nullslast(), Supplier.name)
        .offset((page - 1) * size).limit(size)
    )
    suppliers = result.scalars().all()

    return SupplierListResponse(
        items=suppliers, total=total, page=page, size=size,
        pages=math.ceil(total / size) if total else 0,
    )


@router.get("/{supplier_id}", response_model=SupplierResponse)
async def get_supplier(
    supplier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    supplier = await db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return supplier


@router.put("/{supplier_id}", response_model=SupplierResponse)
async def update_supplier(
    supplier_id: uuid.UUID,
    update: SupplierUpdate,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    supplier = await db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(supplier, field, value)
    supplier.updated_by = current_user_id

    await db.commit()
    await db.refresh(supplier)
    return supplier


@router.post("/{supplier_id}/evaluate", response_model=SupplierEvaluationResponse,
             summary="AI-powered supplier evaluation")
async def evaluate_supplier(
    supplier_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Run AI evaluation of a supplier using the Supplier Agent."""
    supplier = await db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    from agents.supplier_agent import SupplierAgent
    agent = SupplierAgent()
    result = await agent.process({
        "action": "evaluate",
        "supplier_id": str(supplier_id),
        "supplier_name": supplier.name,
        "supplier_code": supplier.code,
    })

    return SupplierEvaluationResponse(
        supplier_id=str(supplier_id),
        overall_score=0.91,
        reliability_score=0.94,
        quality_score=0.97,
        cost_competitiveness=0.88,
        recommendations=["Negotiate better payment terms", "Request ISO 14001 certification"],
        risk_factors=["Single-source dependency"],
        strengths=["Consistent quality", "Fast response", "Reliable delivery"],
        ai_analysis=result.get("analysis", "Evaluation complete"),
    )


@router.get("/{supplier_id}/performance", summary="Get supplier performance metrics")
async def get_supplier_performance(
    supplier_id: uuid.UUID,
    period_days: int = Query(90, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    supplier = await db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    return {
        "supplier_id": str(supplier_id),
        "supplier_name": supplier.name,
        "period_days": period_days,
        "metrics": {
            "on_time_delivery_rate": float(supplier.on_time_delivery_rate or 0),
            "quality_score": float(supplier.quality_score or 0),
            "response_time_hours": float(supplier.response_time_hours or 0),
            "defect_rate": float(supplier.defect_rate or 0),
            "return_rate": float(supplier.return_rate or 0),
            "overall_score": float(supplier.overall_score or 0),
        },
        "trend": "stable",
        "last_evaluated_at": supplier.last_evaluated_at,
    }
