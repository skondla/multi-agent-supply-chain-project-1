"""
Inventory Agent - Manages stock levels, reorders, and warehouse optimization.
Uses Claude with tool-use to check inventory data and make recommendations.
"""
import json
from typing import Any, Dict, List, Optional
import structlog

from agents.base_agent import BaseAgent
from app.core.slack_notifier import SlackLevel

logger = structlog.get_logger()


class InventoryAgent(BaseAgent):
    """
    Specialized agent for inventory management:
    - Real-time stock level checking
    - Low stock detection and reorder triggers
    - Inventory adjustment processing
    - Demand-based replenishment recommendations
    - Warehouse location optimization
    """

    def __init__(self):
        super().__init__(
            name="InventoryAgent",
            description=(
                "Manages inventory levels, detects low stock, triggers reorders, "
                "and optimizes warehouse operations using ML demand forecasts."
            ),
        )

    def _define_tools(self) -> List[Dict]:
        return [
            {
                "name": "check_inventory_level",
                "description": "Check current inventory level for a SKU",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "sku": {"type": "string", "description": "Product SKU"},
                        "warehouse_id": {"type": "string", "description": "Optional warehouse filter"},
                    },
                    "required": ["sku"],
                },
            },
            {
                "name": "get_low_stock_items",
                "description": "Get all items below reorder point",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "warehouse_id": {"type": "string"},
                        "category": {"type": "string"},
                        "limit": {"type": "integer", "default": 50},
                    },
                },
            },
            {
                "name": "calculate_reorder_quantity",
                "description": "Calculate optimal reorder quantity using demand forecast and lead time",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "sku": {"type": "string"},
                        "lead_time_days": {"type": "integer"},
                        "safety_stock_days": {"type": "integer", "default": 7},
                    },
                    "required": ["sku", "lead_time_days"],
                },
            },
            {
                "name": "adjust_inventory",
                "description": "Record an inventory adjustment (increase or decrease)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "sku": {"type": "string"},
                        "quantity_delta": {"type": "integer"},
                        "reason": {"type": "string"},
                        "reference": {"type": "string"},
                    },
                    "required": ["sku", "quantity_delta", "reason"],
                },
            },
            {
                "name": "reserve_inventory",
                "description": "Reserve inventory for an order",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string"},
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "sku": {"type": "string"},
                                    "quantity": {"type": "integer"},
                                },
                            },
                        },
                    },
                    "required": ["order_id", "items"],
                },
            },
            {
                "name": "get_demand_forecast",
                "description": "Get ML demand forecast for a SKU",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "sku": {"type": "string"},
                        "forecast_days": {"type": "integer", "default": 30},
                    },
                    "required": ["sku"],
                },
            },
        ]

    async def _handle_tool(self, tool_name: str, tool_input: Dict) -> Any:
        """Execute inventory tools - integrates with database and ML models."""
        if tool_name == "check_inventory_level":
            # In production: query database
            sku = tool_input["sku"]
            return {
                "sku": sku,
                "quantity_on_hand": 150,
                "quantity_reserved": 25,
                "quantity_available": 125,
                "reorder_point": 50,
                "reorder_quantity": 200,
                "warehouse": tool_input.get("warehouse_id", "WH-001"),
                "is_low_stock": False,
                "unit_cost": 12.50,
                "last_restocked_at": "2025-01-15T10:00:00Z",
            }

        elif tool_name == "get_low_stock_items":
            return {
                "count": 3,
                "items": [
                    {"sku": "SKU-001", "qty_on_hand": 5, "reorder_point": 20, "product_name": "Widget A"},
                    {"sku": "SKU-045", "qty_on_hand": 2, "reorder_point": 15, "product_name": "Gadget B"},
                    {"sku": "SKU-112", "qty_on_hand": 8, "reorder_point": 30, "product_name": "Component C"},
                ],
            }

        elif tool_name == "calculate_reorder_quantity":
            sku = tool_input["sku"]
            lead_time = tool_input.get("lead_time_days", 7)
            safety = tool_input.get("safety_stock_days", 7)
            # EOQ-based calculation
            avg_daily_demand = 25  # Would come from ML model in production
            reorder_qty = (lead_time + safety) * avg_daily_demand
            return {
                "sku": sku,
                "recommended_quantity": reorder_qty,
                "avg_daily_demand": avg_daily_demand,
                "lead_time_days": lead_time,
                "safety_stock_days": safety,
                "calculation_method": "demand_weighted_eoq",
            }

        elif tool_name == "adjust_inventory":
            sku = tool_input["sku"]
            delta = tool_input["quantity_delta"]
            return {
                "sku": sku,
                "adjustment_applied": delta,
                "new_quantity": 150 + delta,
                "reason": tool_input["reason"],
                "adjustment_id": "ADJ-" + sku[:5] + "-001",
                "status": "applied",
            }

        elif tool_name == "reserve_inventory":
            return {
                "order_id": tool_input["order_id"],
                "reserved_items": tool_input["items"],
                "reservation_id": "RES-001",
                "status": "reserved",
                "expires_at": "2025-02-01T00:00:00Z",
            }

        elif tool_name == "get_demand_forecast":
            sku = tool_input["sku"]
            days = tool_input.get("forecast_days", 30)
            return {
                "sku": sku,
                "forecast_days": days,
                "predicted_demand": days * 22,
                "daily_avg": 22,
                "confidence_interval": {"lower": days * 18, "upper": days * 27},
                "trend": "stable",
                "seasonal_factors": {"week": 1.1, "month": 0.95},
                "model_version": "xgb-v2.1",
            }

        return {"error": f"Unknown tool: {tool_name}"}

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Process an inventory management task."""
        action = task.get("action", "analyze")
        sku = task.get("sku")
        order_id = task.get("order_id")

        logger.info("InventoryAgent processing", action=action, sku=sku)

        user_message = f"""Perform the following inventory operation:

Action: {action}
SKU: {sku or 'N/A'}
Order ID: {order_id or 'N/A'}
Data: {json.dumps({k: v for k, v in task.items() if k not in ['action', 'sku', 'order_id']}, default=str)}

Use the available tools to:
1. Check current inventory levels
2. Analyze demand forecasts
3. Make data-driven recommendations
4. Trigger any necessary actions (adjustments, reservations)

Provide specific quantities, costs, and actionable recommendations."""

        messages = [{"role": "user", "content": user_message}]

        final_response, _ = await self.run_agentic_loop(
            initial_messages=messages,
            tool_handler=self._handle_tool,
            max_iterations=8,
        )

        # Check if low stock alert should be sent
        if action in ("check_stock", "analyze", "reorder"):
            await self.notify_slack(
                f"Inventory analysis complete for {sku or 'all SKUs'}",
                level=SlackLevel.INFO,
            )

        return {
            "agent": self.name,
            "action": action,
            "sku": sku,
            "status": "completed",
            "analysis": final_response,
        }

    async def check_availability(self, sku: str, quantity: int) -> Dict[str, Any]:
        """Check if requested quantity is available."""
        result = await self._handle_tool("check_inventory_level", {"sku": sku})
        available = result.get("quantity_available", 0)
        return {
            "sku": sku,
            "requested": quantity,
            "available": available,
            "can_fulfill": available >= quantity,
            "shortfall": max(0, quantity - available),
        }

    async def detect_low_stock(self) -> Dict[str, Any]:
        """Detect all low stock items and optionally trigger reorders."""
        result = await self._handle_tool("get_low_stock_items", {"limit": 100})
        low_stock_items = result.get("items", [])

        if low_stock_items and len(low_stock_items) > 0:
            await self.notify_slack(
                f"{len(low_stock_items)} items are below reorder point and need attention",
                level=SlackLevel.WARNING,
                title="Low Stock Alert",
            )

        return {"low_stock_items": low_stock_items, "count": len(low_stock_items)}

    async def generate_reorder_recommendation(self, sku: str) -> Dict[str, Any]:
        """Generate a reorder recommendation for a specific SKU."""
        inv = await self._handle_tool("check_inventory_level", {"sku": sku})
        forecast = await self._handle_tool("get_demand_forecast", {"sku": sku})
        reorder = await self._handle_tool(
            "calculate_reorder_quantity",
            {"sku": sku, "lead_time_days": inv.get("lead_time_days", 7)},
        )
        return {
            "sku": sku,
            "current_quantity": inv.get("quantity_on_hand"),
            "recommended_quantity": reorder.get("recommended_quantity"),
            "forecast_demand_30d": forecast.get("predicted_demand"),
            "supplier_recommendation": "preferred_supplier_001",
            "estimated_cost": reorder.get("recommended_quantity", 0) * float(inv.get("unit_cost", 0)),
        }
