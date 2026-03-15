"""
Anomaly Detection Agent - Real-time pattern detection, fraud prevention, and supply disruption alerts.
"""
import json
from typing import Any, Dict, List
import structlog

from agents.base_agent import BaseAgent
from app.core.slack_notifier import SlackLevel

logger = structlog.get_logger()


class AnomalyDetectionAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="AnomalyDetectionAgent",
            description=(
                "Detects anomalies in orders, inventory, and supplier behavior. "
                "Identifies fraud, supply disruptions, and operational irregularities "
                "using ensemble ML models and statistical analysis."
            ),
        )

    def _define_tools(self) -> List[Dict]:
        return [
            {
                "name": "detect_order_anomalies",
                "description": "Scan recent orders for suspicious patterns",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "lookback_hours": {"type": "integer", "default": 24},
                        "sensitivity": {"type": "string", "enum": ["low", "medium", "high"], "default": "medium"},
                    },
                },
            },
            {
                "name": "detect_inventory_anomalies",
                "description": "Detect unusual inventory movements or discrepancies",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "warehouse_id": {"type": "string"},
                        "lookback_days": {"type": "integer", "default": 7},
                        "anomaly_types": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "shrinkage, spike, discrepancy, expiry",
                        },
                    },
                },
            },
            {
                "name": "detect_supplier_anomalies",
                "description": "Detect anomalies in supplier behavior and deliveries",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "supplier_id": {"type": "string"},
                        "lookback_days": {"type": "integer", "default": 30},
                    },
                },
            },
            {
                "name": "score_transaction",
                "description": "Score a single transaction for anomaly probability",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "transaction_type": {"type": "string", "enum": ["order", "inventory_adj", "payment", "return"]},
                        "transaction_data": {"type": "object"},
                    },
                    "required": ["transaction_type", "transaction_data"],
                },
            },
            {
                "name": "get_anomaly_history",
                "description": "Get historical anomaly records for analysis",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "entity_type": {"type": "string", "enum": ["order", "inventory", "supplier", "all"]},
                        "severity": {"type": "string", "enum": ["low", "medium", "high", "critical", "all"]},
                        "lookback_days": {"type": "integer", "default": 30},
                        "limit": {"type": "integer", "default": 50},
                    },
                },
            },
            {
                "name": "classify_anomaly",
                "description": "Classify detected anomaly type and recommended action",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "anomaly_id": {"type": "string"},
                        "anomaly_data": {"type": "object"},
                        "context": {"type": "object"},
                    },
                    "required": ["anomaly_data"],
                },
            },
        ]

    async def _handle_tool(self, tool_name: str, tool_input: Dict) -> Any:
        if tool_name == "detect_order_anomalies":
            return {
                "scan_period_hours": tool_input.get("lookback_hours", 24),
                "total_orders_scanned": 847,
                "anomalies_detected": 3,
                "anomalies": [
                    {
                        "id": "ANO-001",
                        "order_id": "ORD-88421",
                        "type": "unusual_quantity",
                        "severity": "medium",
                        "score": 0.78,
                        "description": "Order quantity 50x above customer average",
                        "recommended_action": "manual_review",
                    },
                    {
                        "id": "ANO-002",
                        "order_id": "ORD-88477",
                        "type": "rapid_reorder",
                        "severity": "low",
                        "score": 0.62,
                        "description": "Customer placed 5 orders in 2 hours",
                        "recommended_action": "monitor",
                    },
                    {
                        "id": "ANO-003",
                        "order_id": "ORD-88502",
                        "type": "address_mismatch",
                        "severity": "high",
                        "score": 0.91,
                        "description": "Billing and shipping country mismatch with IP location",
                        "recommended_action": "block_and_review",
                    },
                ],
                "false_positive_estimate": 0.15,
                "model_version": "ensemble-v3.1",
            }

        elif tool_name == "detect_inventory_anomalies":
            return {
                "warehouse_id": tool_input.get("warehouse_id", "ALL"),
                "lookback_days": tool_input.get("lookback_days", 7),
                "anomalies": [
                    {
                        "sku": "SKU-042",
                        "type": "shrinkage",
                        "severity": "high",
                        "expected_qty": 500,
                        "actual_qty": 431,
                        "discrepancy": 69,
                        "discrepancy_value_usd": 862.50,
                        "detection_method": "statistical",
                    },
                    {
                        "sku": "SKU-115",
                        "type": "unexplained_spike",
                        "severity": "medium",
                        "notes": "Inventory increased by 300 units without purchase order",
                        "detection_method": "threshold",
                    },
                ],
                "total_anomalies": 2,
                "total_financial_impact": 1250.00,
            }

        elif tool_name == "detect_supplier_anomalies":
            supplier_id = tool_input.get("supplier_id", "ALL")
            return {
                "supplier_id": supplier_id,
                "anomalies": [
                    {
                        "type": "late_delivery_pattern",
                        "severity": "medium",
                        "frequency": "3 of last 5 deliveries late",
                        "avg_delay_days": 2.4,
                        "trend": "worsening",
                        "recommended_action": "performance_review",
                    }
                ],
                "risk_score": 0.55,
                "is_at_risk": True,
            }

        elif tool_name == "score_transaction":
            txn_type = tool_input["transaction_type"]
            data = tool_input.get("transaction_data", {})
            # Simple scoring heuristic
            amount = float(data.get("amount", data.get("total_amount", 0)))
            base_score = 0.1
            if amount > 10000:
                base_score += 0.3
            if txn_type == "return" and amount > 5000:
                base_score += 0.4
            return {
                "transaction_type": txn_type,
                "anomaly_score": min(base_score, 1.0),
                "risk_level": "high" if base_score > 0.7 else "medium" if base_score > 0.4 else "low",
                "contributing_factors": ["amount_above_threshold"] if amount > 10000 else [],
                "recommended_action": "block" if base_score > 0.8 else "review" if base_score > 0.5 else "allow",
                "model_confidence": 0.85,
            }

        elif tool_name == "get_anomaly_history":
            return {
                "period_days": tool_input.get("lookback_days", 30),
                "total_anomalies": 27,
                "by_severity": {"critical": 2, "high": 8, "medium": 12, "low": 5},
                "by_type": {
                    "fraud_indicator": 7,
                    "inventory_discrepancy": 9,
                    "supplier_issue": 5,
                    "operational": 6,
                },
                "false_positive_rate": 0.11,
                "resolution_rate": 0.89,
                "avg_resolution_hours": 4.2,
            }

        elif tool_name == "classify_anomaly":
            data = tool_input.get("anomaly_data", {})
            score = float(data.get("score", 0.5))
            return {
                "classification": "fraud_indicator" if score > 0.8 else "operational_issue",
                "severity": "critical" if score > 0.9 else "high" if score > 0.7 else "medium",
                "recommended_actions": [
                    "Block transaction pending review",
                    "Notify fraud team",
                    "Request additional verification",
                ] if score > 0.7 else ["Log for monitoring", "Review in next audit"],
                "similar_past_cases": 3,
                "resolution_pattern": "manual_review_resolved_82pct",
                "escalate_to_human": score > 0.85,
            }

        return {"error": f"Unknown tool: {tool_name}"}

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        action = task.get("action", "detect")
        entity_type = task.get("entity_type", "all")

        user_message = f"""Perform anomaly detection for the supply chain:

Action: {action}
Entity Type: {entity_type}
Data: {json.dumps({k: v for k, v in task.items() if k not in ['action', 'entity_type']}, default=str)}

Use the available tools to:
1. Scan for anomalies across orders, inventory, and suppliers
2. Score individual transactions if provided
3. Classify and prioritize detected anomalies
4. Provide specific remediation recommendations
5. Identify any patterns requiring immediate escalation

Flag CRITICAL anomalies immediately with specific action steps."""

        messages = [{"role": "user", "content": user_message}]
        final_response, _ = await self.run_agentic_loop(
            initial_messages=messages,
            tool_handler=self._handle_tool,
            max_iterations=8,
        )

        # Send Slack alert if critical anomalies detected
        if "critical" in final_response.lower() or "block" in final_response.lower():
            await self.notify_slack(
                "Critical anomalies detected in supply chain operations - immediate review required",
                level=SlackLevel.CRITICAL,
                title="Anomaly Alert - Critical",
            )

        return {
            "agent": self.name,
            "action": action,
            "entity_type": entity_type,
            "status": "completed",
            "analysis": final_response,
        }
