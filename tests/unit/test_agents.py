"""
Unit tests for supply chain AI agents.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
@pytest.mark.unit
class TestInventoryAgent:
    """Tests for the Inventory Agent."""

    @pytest.fixture
    def inventory_agent(self, mock_anthropic):
        from agents.inventory_agent import InventoryAgent
        return InventoryAgent()

    async def test_check_availability_sufficient(self, inventory_agent):
        result = await inventory_agent.check_availability("SKU-001", 10)
        assert "available" in result
        assert "can_fulfill" in result
        assert isinstance(result["available"], int)
        assert isinstance(result["can_fulfill"], bool)

    async def test_check_availability_insufficient(self, inventory_agent):
        result = await inventory_agent.check_availability("SKU-001", 9999)
        # Requesting more than available should indicate shortfall
        assert "shortfall" in result
        if not result["can_fulfill"]:
            assert result["shortfall"] > 0

    async def test_detect_low_stock_returns_list(self, inventory_agent, mock_slack):
        result = await inventory_agent.detect_low_stock()
        assert "low_stock_items" in result
        assert "count" in result
        assert isinstance(result["low_stock_items"], list)

    async def test_generate_reorder_recommendation(self, inventory_agent):
        result = await inventory_agent.generate_reorder_recommendation("SKU-001")
        assert "sku" in result
        assert "recommended_quantity" in result
        assert "forecast_demand_30d" in result
        assert result["recommended_quantity"] > 0

    async def test_check_inventory_tool(self, inventory_agent):
        result = await inventory_agent._handle_tool(
            "check_inventory_level", {"sku": "SKU-001"}
        )
        assert result["sku"] == "SKU-001"
        assert "quantity_on_hand" in result
        assert "quantity_available" in result
        assert result["quantity_available"] >= 0

    async def test_calculate_reorder_tool(self, inventory_agent):
        result = await inventory_agent._handle_tool(
            "calculate_reorder_quantity",
            {"sku": "SKU-001", "lead_time_days": 7, "safety_stock_days": 7},
        )
        assert "recommended_quantity" in result
        assert result["recommended_quantity"] > 0
        assert result["lead_time_days"] == 7

    async def test_adjust_inventory_tool(self, inventory_agent):
        result = await inventory_agent._handle_tool(
            "adjust_inventory",
            {"sku": "SKU-001", "quantity_delta": 50, "reason": "Purchase order received"},
        )
        assert result["status"] == "applied"
        assert result["adjustment_applied"] == 50

    async def test_agent_status(self, inventory_agent):
        status = inventory_agent.get_status()
        assert status["name"] == "InventoryAgent"
        assert status["status"] == "active"
        assert "total_requests" in status
        assert "success_rate" in status


@pytest.mark.asyncio
@pytest.mark.unit
class TestOrderAgent:
    """Tests for the Order Agent."""

    @pytest.fixture
    def order_agent(self, mock_anthropic):
        from agents.order_agent import OrderAgent
        return OrderAgent()

    async def test_validate_order_valid(self, order_agent):
        result = await order_agent.validate_order({
            "customer_id": "cust-001",
            "items": [{"sku": "A", "quantity": 5, "unit_price": 10.00}],
        })
        assert "is_valid" in result
        assert "errors" in result

    async def test_validate_order_invalid_quantity(self, order_agent):
        result = await order_agent._handle_tool("validate_order", {
            "customer_id": "cust-001",
            "items": [{"sku": "A", "quantity": -1, "unit_price": 10.00}],
        })
        assert result["is_valid"] is False
        assert len(result["errors"]) > 0

    async def test_fraud_check_normal_order(self, order_agent):
        result = await order_agent.check_fraud_indicators({
            "customer_id": "cust-established-001",
            "total_amount": 250.00,
            "items": [{"sku": "A", "quantity": 2}],
        })
        assert "fraud_score" in result
        assert "risk_level" in result
        assert result["fraud_score"] <= 1.0
        assert result["fraud_score"] >= 0.0

    async def test_fraud_check_high_value_order(self, order_agent):
        result = await order_agent._handle_tool("check_fraud_indicators", {
            "customer_id": "new-customer",
            "order_amount": 75000.00,
            "items": [{"sku": "expensive", "quantity": 100}],
        })
        assert result["fraud_score"] > 0.3
        assert result["requires_review"] is True

    async def test_calculate_order_total(self, order_agent):
        result = await order_agent._handle_tool("calculate_order_total", {
            "items": [
                {"sku": "A", "quantity": 2, "unit_price": 50.00},
                {"sku": "B", "quantity": 1, "unit_price": 30.00},
            ],
            "shipping_address": {"country": "US"},
        })
        assert result["subtotal"] == 130.00
        assert result["total"] > result["subtotal"]  # Tax added
        assert result["tax"] > 0

    async def test_sla_check_tool(self, order_agent):
        result = await order_agent._handle_tool("check_sla_compliance", {
            "order_id": "ORD-001",
            "priority": "high",
        })
        assert "sla_target_hours" in result
        assert result["sla_target_hours"] == 8  # High priority = 8h SLA
        assert "is_compliant" in result

    async def test_customer_history_tool(self, order_agent):
        result = await order_agent._handle_tool("get_customer_history", {
            "customer_id": "cust-001"
        })
        assert "total_orders" in result
        assert "risk_profile" in result
        assert result["total_orders"] >= 0


@pytest.mark.asyncio
@pytest.mark.unit
class TestOrchestratorAgent:
    """Tests for the Orchestrator Agent."""

    @pytest.fixture
    def orchestrator(self, mock_anthropic):
        from agents.orchestrator_agent import OrchestratorAgent
        return OrchestratorAgent()

    async def test_orchestrator_tool_definition(self, orchestrator):
        tools = orchestrator._define_tools()
        assert len(tools) >= 4
        tool_names = [t["name"] for t in tools]
        assert "analyze_task" in tool_names
        assert "route_to_agent" in tool_names
        assert "aggregate_results" in tool_names
        assert "send_notification" in tool_names

    async def test_handle_analyze_task(self, orchestrator):
        result = await orchestrator._handle_tool("analyze_task", {
            "task_type": "order_processing",
            "priority": "high",
            "agents_needed": ["order", "inventory"],
            "execution_strategy": "sequential",
            "reasoning": "Order requires inventory check before processing",
        })
        assert result["status"] == "analysis_complete"
        assert "analysis" in result

    async def test_handle_unknown_tool(self, orchestrator):
        result = await orchestrator._handle_tool("nonexistent_tool", {})
        assert "error" in result

    async def test_orchestrator_status(self, orchestrator):
        status = orchestrator.get_status()
        assert status["name"] == "OrchestratorAgent"
        assert status["model"] == "claude-opus-4-6"

    async def test_route_to_valid_agent(self, orchestrator):
        result = await orchestrator._handle_tool("route_to_agent", {
            "agent_name": "inventory",
            "task_data": {"sku": "SKU-001"},
            "action": "check_stock",
        })
        assert "agent" in result
        assert result["agent"] == "inventory"

    async def test_aggregate_results_tool(self, orchestrator):
        result = await orchestrator._handle_tool("aggregate_results", {
            "results": [{"agent": "inventory", "status": "ok"}],
            "summary": "All agents completed successfully",
            "action_items": ["Reorder SKU-001"],
        })
        assert result["status"] == "aggregated"


@pytest.mark.asyncio
@pytest.mark.unit
class TestAnomalyDetectionAgent:
    """Tests for the Anomaly Detection Agent."""

    @pytest.fixture
    def anomaly_agent(self, mock_anthropic):
        from agents.anomaly_detection_agent import AnomalyDetectionAgent
        return AnomalyDetectionAgent()

    async def test_detect_order_anomalies(self, anomaly_agent):
        result = await anomaly_agent._handle_tool("detect_order_anomalies", {
            "lookback_hours": 24,
            "sensitivity": "medium",
        })
        assert "anomalies_detected" in result
        assert "total_orders_scanned" in result
        assert isinstance(result["anomalies"], list)

    async def test_score_transaction_normal(self, anomaly_agent):
        result = await anomaly_agent._handle_tool("score_transaction", {
            "transaction_type": "order",
            "transaction_data": {"amount": 150.00, "customer_id": "cust-001"},
        })
        assert 0.0 <= result["anomaly_score"] <= 1.0
        assert result["risk_level"] in ("low", "medium", "high")
        assert result["recommended_action"] in ("allow", "review", "block")

    async def test_score_high_value_transaction(self, anomaly_agent):
        result = await anomaly_agent._handle_tool("score_transaction", {
            "transaction_type": "order",
            "transaction_data": {"amount": 75000.00},
        })
        assert result["anomaly_score"] > 0.3
        assert result["risk_level"] in ("medium", "high")

    async def test_detect_inventory_anomalies(self, anomaly_agent):
        result = await anomaly_agent._handle_tool("detect_inventory_anomalies", {
            "lookback_days": 7,
        })
        assert "anomalies" in result
        assert "total_anomalies" in result

    async def test_classify_anomaly(self, anomaly_agent):
        result = await anomaly_agent._handle_tool("classify_anomaly", {
            "anomaly_data": {"score": 0.92, "type": "fraud_indicator"},
        })
        assert "classification" in result
        assert "severity" in result
        assert "recommended_actions" in result
        assert isinstance(result["recommended_actions"], list)


@pytest.mark.asyncio
@pytest.mark.unit
class TestDemandForecastAgent:
    """Tests for the Demand Forecast Agent."""

    @pytest.fixture
    def forecast_agent(self, mock_anthropic):
        from agents.demand_forecast_agent import DemandForecastAgent
        return DemandForecastAgent()

    async def test_get_demand_forecast(self, forecast_agent):
        result = await forecast_agent._handle_tool("get_demand_forecast", {
            "sku": "SKU-001",
            "forecast_horizon_days": 30,
        })
        assert result["sku"] == "SKU-001"
        assert "predicted_total_demand" in result
        assert "daily_average" in result
        assert result["predicted_total_demand"] > 0
        assert "confidence_intervals" in result

    async def test_assess_stockout_risk_safe(self, forecast_agent):
        result = await forecast_agent._handle_tool("assess_stockout_risk", {
            "sku": "SKU-001",
            "current_qty": 500,
            "lead_time_days": 7,
        })
        assert result["stockout_risk"] == "low"
        assert result["days_of_supply"] > result["lead_time_days"]

    async def test_assess_stockout_risk_high(self, forecast_agent):
        result = await forecast_agent._handle_tool("assess_stockout_risk", {
            "sku": "SKU-CRITICAL",
            "current_qty": 5,
            "lead_time_days": 7,
        })
        # 5 units / 25 daily avg = 0.2 days of supply < 7 day lead time
        assert result["stockout_risk"] == "high"
        assert result["recommended_action"] == "immediate_reorder"

    async def test_analyze_demand_trends(self, forecast_agent):
        result = await forecast_agent._handle_tool("analyze_demand_trends", {
            "sku": "SKU-001",
            "lookback_days": 365,
        })
        assert "trend" in result
        assert "seasonality" in result
        assert "volatility" in result

    async def test_generate_replenishment_plan(self, forecast_agent):
        result = await forecast_agent._handle_tool("generate_replenishment_plan", {
            "skus": ["SKU-001", "SKU-002", "SKU-003"],
            "planning_horizon_days": 30,
        })
        assert "plan_items" in result
        assert "total_estimated_cost" in result
        assert len(result["plan_items"]) <= 3
        assert result["total_estimated_cost"] >= 0
