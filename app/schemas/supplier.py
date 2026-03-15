"""
Pydantic v2 schemas for Supplier API endpoints.
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, EmailStr

from app.models.supplier import SupplierStatus


class AddressInput(BaseModel):
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    country: str


class SupplierCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    code: str = Field(..., min_length=1, max_length=50)
    contact_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    address: Optional[AddressInput] = None
    country: Optional[str] = None
    region: Optional[str] = None
    payment_terms: str = "NET30"
    lead_time_days: int = Field(7, ge=0, le=365)
    minimum_order_value: Decimal = Field(0, ge=0)
    currency: str = "USD"
    categories: List[str] = []
    certifications: List[str] = []
    notes: Optional[str] = None
    tags: List[str] = []


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[SupplierStatus] = None
    contact_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    payment_terms: Optional[str] = None
    lead_time_days: Optional[int] = Field(None, ge=0)
    minimum_order_value: Optional[Decimal] = None
    categories: Optional[List[str]] = None
    certifications: Optional[List[str]] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    contract_end: Optional[datetime] = None


class SupplierPerformanceUpdate(BaseModel):
    reliability_score: Optional[Decimal] = Field(None, ge=0, le=1)
    quality_score: Optional[Decimal] = Field(None, ge=0, le=1)
    on_time_delivery_rate: Optional[Decimal] = Field(None, ge=0, le=1)
    response_time_hours: Optional[Decimal] = Field(None, ge=0)
    defect_rate: Optional[Decimal] = Field(None, ge=0, le=1)
    return_rate: Optional[Decimal] = Field(None, ge=0, le=1)


class SupplierResponse(BaseModel):
    id: UUID
    name: str
    code: str
    status: SupplierStatus
    contact_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    payment_terms: str
    lead_time_days: int
    minimum_order_value: Decimal
    currency: str
    categories: List[str]
    certifications: List[str]
    reliability_score: Optional[Decimal] = None
    quality_score: Optional[Decimal] = None
    on_time_delivery_rate: Optional[Decimal] = None
    response_time_hours: Optional[Decimal] = None
    overall_score: Optional[Decimal] = None
    is_preferred: bool
    is_at_risk: bool
    total_orders: int
    total_spend: Optional[Decimal] = None
    last_evaluated_at: Optional[datetime] = None
    notes: Optional[str] = None
    tags: List[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SupplierEvaluationResponse(BaseModel):
    supplier_id: str
    overall_score: float
    reliability_score: float
    quality_score: float
    cost_competitiveness: float
    recommendations: List[str]
    risk_factors: List[str]
    strengths: List[str]
    ai_analysis: str


class SupplierListResponse(BaseModel):
    items: List[SupplierResponse]
    total: int
    page: int
    size: int
    pages: int
