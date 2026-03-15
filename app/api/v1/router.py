"""
API v1 main router - aggregates all endpoint routers.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import orders, inventory, suppliers, shipments, agents, auth, analytics

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(orders.router, prefix="/orders", tags=["orders"])
api_router.include_router(inventory.router, prefix="/inventory", tags=["inventory"])
api_router.include_router(suppliers.router, prefix="/suppliers", tags=["suppliers"])
api_router.include_router(shipments.router, prefix="/shipments", tags=["shipments"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
