"""
Demand Forecast Agent - ML-powered demand prediction and replenishment planning.
"""
import json
from typing import Any, Dict, List
import structlog

from agents.base_agent import BaseAgent
from app.core.slack_notifier import SlackLevel

logger = structlog.get_logger()


class DemandForecastAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="DemandForecastAgent",
            description=(
                "Uses ML models to forecast demand, identify trends, detect seasonality, "
                "and generate replenishment recommendations for supply chain optimization."
            ),
        )

    def _define_tools(self) -> List[Dict]:
        return [
            {
                "name": "get_demand_forecast",
                "description": "Get ML demand forecast for a SKU or category",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "sku": {"type": "string"},
                        "category": {"type": "string"},
                        "forecast_horizon_days": {"type": "integer", "default": 30},
                        "include_confidence_intervals": {"type": "boolean", "default": True},
                    },
                },
            },
            {
                "name": "analyze_demand_trends",
                "description": "Analyze historical demand trends and seasonality patterns",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "sku": {"type": "string"},
                        "lookback_days": {"type": "integer", "default": 365},
                        "granularity": {"type": "string", "enum": ["daily", "weekly", "monthly"], "default": "weekly"},
                    },
                },
            },
            {
                "name": "detect_demand_anomaly",
                "description": "Detect anomalous demand spikes or drops",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "sku": {"type": "string"},
                        "threshold_sigma": {"type": "number", "default": 2.5},
                    },
                    "required": ["sku"],
                },
            },
            {
                "name": "generate_replenishment_plan",
                "description": "Generate optimal replenishment plan based on forecast",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "skus": {"type": "array", "items": {"type": "string"}},
                        "planning_horizon_days": {"type": "integer", "default": 30},
                        "budget_limit": {"type": "number"},
                        "service_level_target": {"type": "number", "default": 0.95},
                    },
                    "required": ["skus"],
                },
            },
            {
                "name": "assess_stockout_risk",
                "description": "Assess risk of stockout for inventory items",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "sku": {"type": "string"},
                        "current_qty": {"type": "integer"},
                        "lead_time_days": {"type": "integer"},
                    },
                    "required": ["sku"],
                },
            },
        ]

    async def _handle_tool(self, tool_name: str, tool_input: Dict) -> Any:
        if tool_name == "get_demand_forecast":
            sku = tool_input.get("sku", "ALL")
            days = tool_input.get("forecast_horizon_days", 30)
            daily_avg = 25.3
            predicted = daily_avg * days
            return {
                "sku": sku,
                "forecast_horizon_days": days,
                "predicted_total_demand": round(predicted, 1),
                "daily_average": daily_avg,
                "weekly_average": round(daily_avg * 7, 1),
                "confidence_intervals": {
                    "80_pct": {"lower": round(predicted * 0.88, 1), "upper": round(predicted * 1.13, 1)},
                    "95_pct": {"lower": round(predicted * 0.78, 1), "upper": round(predicted * 1.23, 1)},
                },
                "trend": "slight_upward",
                "trend_pct_change": 3.2,
                "seasonality_detected": True,
                "seasonal_peak_month": "December",
                "model_accuracy_mape": 0.087,
                "model_version": "xgb-v2.3.1",
                "last_trained": "2025-01-10",
            }

        elif tool_name == "analyze_demand_trends":
            sku = tool_input.get("sku", "SKU-001")
            return {
                "sku": sku,
                "lookback_days": tool_input.get("lookback_days", 365),
                "trend": {
                    "direction": "upward",
                    "strength": "moderate",
                    "annual_growth_rate": 0.082,
                },
                "seasonality": {
                    "detected": True,
                    "period_days": 7,
                    "amplitude": 0.28,
                    "peak_days": ["Friday", "Saturday"],
                    "trough_days": ["Tuesday", "Wednesday"],
                    "annual_peak_months": ["November", "December"],
                },
                "volatility": {
                    "coefficient_of_variation": 0.18,
                    "is_volatile": False,
                },
                "anomalies_detected": 3,
                "anomaly_impact_pct": 0.04,
            }

        elif tool_name == "detect_demand_anomaly":
            sku = tool_input["sku"]
            return {
                "sku": sku,
                "anomalies": [
                    {
                        "date": "2025-01-05",
                        "actual_demand": 180,
                        "expected_demand": 25,
                        "z_score": 4.2,
                        "type": "spike",
                        "probable_cause": "promotional_event",
                    }
                ],
                "total_anomalies": 1,
                "impact_on_forecast": "low",
                "threshold_sigma": tool_input.get("threshold_sigma", 2.5),
            }

        elif tool_name == "generate_replenishment_plan":
            skus = tool_input.get("skus", [])
            horizon = tool_input.get("planning_horizon_days", 30)
            plan_items = []
            total_cost = 0
            for sku in skus[:10]:  # Limit to 10 for demo
                qty = 200
                cost = qty * 12.50
                total_cost += cost
                plan_items.append({
                    "sku": sku,
                    "current_stock": 45,
                    "forecast_demand": 25 * horizon,
                    "recommended_order_qty": qty,
                    "estimated_cost": cost,
                    "order_by_date": "2025-02-01",
                    "suggested_supplier": "SUP-001",
                    "priority": "high" if 45 < 50 else "medium",
                })
            return {
                "planning_horizon_days": horizon,
                "total_skus": len(skus),
                "total_estimated_cost": total_cost,
                "service_level_target": tool_input.get("service_level_target", 0.95),
                "plan_items": plan_items,
                "budget_utilized": min(total_cost, tool_input.get("budget_limit", total_cost)),
                "generated_at": "2025-01-20T12:00:00Z",
            }

        elif tool_name == "assess_stockout_risk":
            sku = tool_input["sku"]
            current_qty = tool_input.get("current_qty", 50)
            lead_time = tool_input.get("lead_time_days", 7)
            daily_demand = 25
            days_of_supply = current_qty / daily_demand if daily_demand > 0 else 999
            return {
                "sku": sku,
                "current_qty": current_qty,
                "days_of_supply": round(days_of_supply, 1),
                "lead_time_days": lead_time,
                "buffer_days": round(days_of_supply - lead_time, 1),
                "stockout_risk": "high" if days_of_supply < lead_time else "medium" if days_of_supply < lead_time * 1.5 else "low",
                "stockout_probability_pct": round(max(0, min(100, (lead_time - days_of_supply) / lead_time * 100)), 1),
                "recommended_action": "immediate_reorder" if days_of_supply < lead_time else "monitor",
            }

        return {"error": f"Unknown tool: {tool_name}"}

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        action = task.get("action", "forecast")
        sku = task.get("sku")

        user_message = f"""Perform the following demand forecasting task:

Action: {action}
SKU: {sku or 'portfolio-wide'}
Data: {json.dumps({k: v for k, v in task.items() if k not in ['action', 'sku']}, default=str)}

Use ML forecasting tools to:
1. Generate accurate demand forecasts
2. Analyze trends and seasonality
3. Detect any demand anomalies
4. Assess stockout risks
5. Provide specific replenishment recommendations with quantities and dates"""

        messages = [{"role": "user", "content": user_message}]
        final_response, _ = await self.run_agentic_loop(
            initial_messages=messages,
            tool_handler=self._handle_tool,
            max_iterations=8,
        )

        return {"agent": self.name, "action": action, "sku": sku, "status": "completed", "analysis": final_response}
