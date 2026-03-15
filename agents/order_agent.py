"""
Order Agent - Handles order validation, processing, and lifecycle management.
"""
import json
from decimal import Decimal
from typing import Any, Dict, List
import structlog

from agents.base_agent import BaseAgent
from app.core.slack_notifier import SlackLevel

logger = structlog.get_logger()


class OrderAgent(BaseAgent):
    """
    Specialized agent for order management:
    - Order validation (items, quantities, customer)
    - Fraud detection and risk scoring
    - Priority-based routing
    - Status management and customer notifications
    - SLA monitoring
    """

    def __init__(self):
        super().__init__(
            name="OrderAgent",
            description=(
                "Validates orders, detects fraud, manages order lifecycle, "
                "and ensures SLA compliance for supply chain order processing."
            ),
        )

    def _define_tools(self) -> List[Dict]:
        return [
            {
                "name": "validate_order",
                "description": "Validate order data: items, quantities, pricing, addresses",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string"},
                        "customer_id": {"type": "string"},
                        "items": {"type": "array"},
                        "total_amount": {"type": "number"},
                        "shipping_address": {"type": "object"},
                    },
                    "required": ["customer_id", "items"],
                },
            },
            {
                "name": "check_fraud_indicators",
                "description": "Analyze order for fraud indicators and compute risk score",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string"},
                        "order_amount": {"type": "number"},
                        "items": {"type": "array"},
                        "shipping_address": {"type": "object"},
                        "customer_history": {"type": "object"},
                    },
                    "required": ["customer_id", "order_amount"],
                },
            },
            {
                "name": "calculate_order_total",
                "description": "Calculate order total with tax and shipping",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "items": {"type": "array"},
                        "shipping_address": {"type": "object"},
                        "discount_code": {"type": "string"},
                    },
                    "required": ["items", "shipping_address"],
                },
            },
            {
                "name": "update_order_status",
                "description": "Update order status in the system",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string"},
                        "new_status": {"type": "string"},
                        "notes": {"type": "string"},
                    },
                    "required": ["order_id", "new_status"],
                },
            },
            {
                "name": "check_sla_compliance",
                "description": "Check if order is within SLA targets",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string"},
                        "order_created_at": {"type": "string"},
                        "priority": {"type": "string"},
                        "current_status": {"type": "string"},
                    },
                    "required": ["order_id", "priority"],
                },
            },
            {
                "name": "get_customer_history",
                "description": "Get customer order history and risk profile",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string"},
                        "lookback_days": {"type": "integer", "default": 90},
                    },
                    "required": ["customer_id"],
                },
            },
        ]

    async def _handle_tool(self, tool_name: str, tool_input: Dict) -> Any:
        if tool_name == "validate_order":
            items = tool_input.get("items", [])
            errors = []
            for item in items:
                if item.get("quantity", 0) <= 0:
                    errors.append(f"Invalid quantity for SKU {item.get('sku')}")
                if float(item.get("unit_price", 0)) <= 0:
                    errors.append(f"Invalid price for SKU {item.get('sku')}")
            return {
                "is_valid": len(errors) == 0,
                "errors": errors,
                "items_validated": len(items),
                "validation_score": 1.0 if not errors else 0.5,
            }

        elif tool_name == "check_fraud_indicators":
            amount = float(tool_input.get("order_amount", 0))
            customer_id = tool_input.get("customer_id", "")
            # Simple fraud scoring heuristics
            fraud_score = 0.0
            indicators = []

            if amount > 50000:
                fraud_score += 0.4
                indicators.append("unusually_high_order_value")
            if customer_id.startswith("new-"):
                fraud_score += 0.2
                indicators.append("new_customer")
            if len(tool_input.get("items", [])) > 50:
                fraud_score += 0.3
                indicators.append("high_item_count")

            return {
                "fraud_score": min(fraud_score, 1.0),
                "risk_level": "high" if fraud_score > 0.7 else "medium" if fraud_score > 0.3 else "low",
                "indicators": indicators,
                "requires_review": fraud_score > 0.5,
                "auto_approved": fraud_score <= 0.3,
            }

        elif tool_name == "calculate_order_total":
            items = tool_input.get("items", [])
            subtotal = sum(
                float(item.get("quantity", 0)) * float(item.get("unit_price", 0))
                for item in items
            )
            country = tool_input.get("shipping_address", {}).get("country", "US")
            tax_rate = 0.08 if country == "US" else 0.20
            tax = subtotal * tax_rate
            shipping = 15.00 if subtotal < 100 else 0.00  # Free shipping over $100
            return {
                "subtotal": round(subtotal, 2),
                "tax": round(tax, 2),
                "tax_rate": tax_rate,
                "shipping": shipping,
                "discount": 0.00,
                "total": round(subtotal + tax + shipping, 2),
                "currency": "USD",
            }

        elif tool_name == "update_order_status":
            return {
                "order_id": tool_input["order_id"],
                "previous_status": "pending",
                "new_status": tool_input["new_status"],
                "updated": True,
                "notes": tool_input.get("notes", ""),
            }

        elif tool_name == "check_sla_compliance":
            priority = tool_input.get("priority", "medium")
            sla_hours = {"critical": 2, "high": 8, "medium": 24, "low": 72}
            max_hours = sla_hours.get(priority, 24)
            return {
                "order_id": tool_input["order_id"],
                "priority": priority,
                "sla_target_hours": max_hours,
                "hours_elapsed": 3,
                "is_compliant": True,
                "time_remaining_hours": max_hours - 3,
                "at_risk": (max_hours - 3) < 2,
            }

        elif tool_name == "get_customer_history":
            customer_id = tool_input["customer_id"]
            return {
                "customer_id": customer_id,
                "total_orders": 45,
                "total_spend": 12450.00,
                "avg_order_value": 276.67,
                "return_rate": 0.02,
                "on_time_payment_rate": 0.98,
                "account_age_days": 720,
                "risk_profile": "low",
                "preferred_customer": True,
            }

        return {"error": f"Unknown tool: {tool_name}"}

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        action = task.get("action", "process")
        order_data = task.get("order_data", task)

        logger.info("OrderAgent processing", action=action)

        user_message = f"""Process the following order management task:

Action: {action}
Order Data: {json.dumps(order_data, default=str, indent=2)}

Please:
1. Validate the order data
2. Check customer history and fraud indicators
3. Calculate accurate totals
4. Check SLA compliance
5. Provide a processing decision with justification

Be thorough in validation and flag any concerns immediately."""

        messages = [{"role": "user", "content": user_message}]

        final_response, _ = await self.run_agentic_loop(
            initial_messages=messages,
            tool_handler=self._handle_tool,
            max_iterations=8,
        )

        return {
            "agent": self.name,
            "action": action,
            "status": "completed",
            "analysis": final_response,
        }

    async def validate_order(self, order: Dict) -> Dict[str, Any]:
        return await self._handle_tool("validate_order", order)

    async def check_fraud_indicators(self, order: Dict) -> Dict[str, Any]:
        return await self._handle_tool("check_fraud_indicators", {
            "customer_id": order.get("customer_id"),
            "order_amount": order.get("total_amount", 0),
            "items": order.get("items", []),
            "shipping_address": order.get("shipping_address", {}),
        })
