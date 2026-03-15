"""
Supplier Agent - Manages vendor evaluation, scoring, and recommendations.
"""
import json
from typing import Any, Dict, List
import structlog

from agents.base_agent import BaseAgent
from app.core.slack_notifier import SlackLevel

logger = structlog.get_logger()


class SupplierAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="SupplierAgent",
            description=(
                "Evaluates supplier performance, manages vendor relationships, "
                "and recommends optimal suppliers for procurement decisions."
            ),
        )

    def _define_tools(self) -> List[Dict]:
        return [
            {
                "name": "get_supplier_performance",
                "description": "Get performance metrics for a supplier",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "supplier_id": {"type": "string"},
                        "period_days": {"type": "integer", "default": 90},
                    },
                    "required": ["supplier_id"],
                },
            },
            {
                "name": "evaluate_supplier",
                "description": "Run comprehensive AI evaluation of a supplier",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "supplier_id": {"type": "string"},
                        "evaluation_criteria": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["supplier_id"],
                },
            },
            {
                "name": "recommend_suppliers",
                "description": "Recommend best suppliers for a category or SKU",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string"},
                        "sku": {"type": "string"},
                        "quantity": {"type": "integer"},
                        "required_lead_time_days": {"type": "integer"},
                        "top_n": {"type": "integer", "default": 3},
                    },
                },
            },
            {
                "name": "check_contract_compliance",
                "description": "Check if supplier is meeting contract terms",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "supplier_id": {"type": "string"},
                        "contract_start": {"type": "string"},
                        "contract_end": {"type": "string"},
                    },
                    "required": ["supplier_id"],
                },
            },
            {
                "name": "generate_rfq",
                "description": "Generate a Request for Quotation for a supplier",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "supplier_id": {"type": "string"},
                        "items": {"type": "array"},
                        "delivery_date": {"type": "string"},
                        "special_requirements": {"type": "string"},
                    },
                    "required": ["supplier_id", "items"],
                },
            },
        ]

    async def _handle_tool(self, tool_name: str, tool_input: Dict) -> Any:
        if tool_name == "get_supplier_performance":
            return {
                "supplier_id": tool_input["supplier_id"],
                "period_days": tool_input.get("period_days", 90),
                "on_time_delivery_rate": 0.94,
                "quality_score": 0.97,
                "response_time_hours": 4.2,
                "defect_rate": 0.008,
                "return_rate": 0.015,
                "total_orders": 127,
                "total_spend": 248500.00,
                "outstanding_issues": 2,
                "certifications_valid": True,
            }

        elif tool_name == "evaluate_supplier":
            supplier_id = tool_input["supplier_id"]
            # AI scoring computation
            scores = {
                "reliability": 0.94,
                "quality": 0.97,
                "cost_competitiveness": 0.88,
                "responsiveness": 0.91,
                "compliance": 0.96,
                "innovation": 0.75,
            }
            overall = sum(scores.values()) / len(scores)
            return {
                "supplier_id": supplier_id,
                "overall_score": round(overall, 4),
                "scores": scores,
                "risk_level": "low" if overall > 0.85 else "medium" if overall > 0.70 else "high",
                "recommendation": "preferred" if overall > 0.85 else "standard",
                "strengths": ["consistent quality", "fast response time", "reliable delivery"],
                "improvement_areas": ["pricing negotiation", "product innovation"],
                "ai_analysis": f"Supplier {supplier_id} demonstrates strong performance with 94% on-time delivery and minimal defect rates.",
            }

        elif tool_name == "recommend_suppliers":
            return {
                "recommendations": [
                    {
                        "supplier_id": "SUP-001",
                        "name": "Premier Supply Co",
                        "score": 0.96,
                        "lead_time_days": 5,
                        "price_competitiveness": "excellent",
                        "certifications": ["ISO9001", "ISO14001"],
                    },
                    {
                        "supplier_id": "SUP-003",
                        "name": "Global Parts Ltd",
                        "score": 0.91,
                        "lead_time_days": 7,
                        "price_competitiveness": "good",
                        "certifications": ["ISO9001"],
                    },
                    {
                        "supplier_id": "SUP-007",
                        "name": "FastShip Components",
                        "score": 0.88,
                        "lead_time_days": 3,
                        "price_competitiveness": "fair",
                        "certifications": ["ISO9001", "AS9100"],
                    },
                ],
                "category": tool_input.get("category"),
                "recommendation_basis": "performance_score_weighted",
            }

        elif tool_name == "check_contract_compliance":
            return {
                "supplier_id": tool_input["supplier_id"],
                "is_compliant": True,
                "compliance_score": 0.96,
                "violations": [],
                "warnings": ["Contract renewal due in 45 days"],
                "next_review_date": "2025-06-01",
            }

        elif tool_name == "generate_rfq":
            return {
                "rfq_id": "RFQ-2025-001",
                "supplier_id": tool_input["supplier_id"],
                "items": tool_input.get("items", []),
                "status": "generated",
                "deadline": "2025-02-15",
                "rfq_document": "Generated RFQ with standard terms, pricing sheets, and delivery requirements.",
                "contact_instructions": "Send to procurement@supplier.com with reference RFQ-2025-001",
            }

        return {"error": f"Unknown tool: {tool_name}"}

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        action = task.get("action", "evaluate")
        supplier_id = task.get("supplier_id")

        user_message = f"""Perform the following supplier management task:

Action: {action}
Supplier ID: {supplier_id or 'N/A'}
Data: {json.dumps({k: v for k, v in task.items() if k not in ['action', 'supplier_id']}, default=str)}

Use the available tools to gather supplier performance data, conduct evaluation,
and provide specific, actionable recommendations. Include concrete scores and
comparison against benchmarks."""

        messages = [{"role": "user", "content": user_message}]
        final_response, _ = await self.run_agentic_loop(
            initial_messages=messages,
            tool_handler=self._handle_tool,
            max_iterations=8,
        )

        return {
            "agent": self.name,
            "action": action,
            "supplier_id": supplier_id,
            "status": "completed",
            "analysis": final_response,
        }
