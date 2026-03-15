"""
Orchestrator Agent - Central coordinator for all supply chain agents.
Routes tasks to specialized agents, aggregates results, and provides
unified responses using Claude's multi-step reasoning.
"""
import asyncio
import json
import time
import uuid
from typing import Any, Dict, List, Optional
import structlog

from agents.base_agent import BaseAgent
from app.core.config import settings
from app.core.slack_notifier import SlackLevel

logger = structlog.get_logger()


class OrchestratorAgent(BaseAgent):
    """
    Central orchestrator that:
    1. Analyzes incoming supply chain tasks
    2. Determines which specialized agents to invoke
    3. Coordinates parallel or sequential execution
    4. Aggregates results into actionable insights
    5. Sends Slack notifications at each stage
    """

    def __init__(self):
        super().__init__(
            name="OrchestratorAgent",
            description=(
                "Central coordinator for supply chain multi-agent orchestration. "
                "Analyzes tasks, routes to specialized agents, and aggregates results."
            ),
        )
        # Lazy-load specialized agents to avoid circular imports
        self._agents: Dict[str, BaseAgent] = {}

    def _get_agent(self, name: str) -> BaseAgent:
        """Lazy-load and cache specialized agents."""
        if name not in self._agents:
            from agents.inventory_agent import InventoryAgent
            from agents.order_agent import OrderAgent
            from agents.supplier_agent import SupplierAgent
            from agents.logistics_agent import LogisticsAgent
            from agents.demand_forecast_agent import DemandForecastAgent
            from agents.anomaly_detection_agent import AnomalyDetectionAgent

            agent_map = {
                "inventory": InventoryAgent,
                "order": OrderAgent,
                "supplier": SupplierAgent,
                "logistics": LogisticsAgent,
                "demand_forecast": DemandForecastAgent,
                "anomaly_detection": AnomalyDetectionAgent,
            }
            if name in agent_map:
                self._agents[name] = agent_map[name]()
        return self._agents.get(name)

    def _define_tools(self) -> List[Dict]:
        return [
            {
                "name": "analyze_task",
                "description": (
                    "Analyze a supply chain task to determine routing strategy, "
                    "which agents to invoke, and in what order."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "task_type": {
                            "type": "string",
                            "enum": [
                                "order_processing",
                                "inventory_check",
                                "supplier_evaluation",
                                "logistics_optimization",
                                "demand_forecasting",
                                "anomaly_detection",
                                "comprehensive_analysis",
                            ],
                            "description": "Primary task type",
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["low", "medium", "high", "critical"],
                        },
                        "agents_needed": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of agent names to invoke",
                        },
                        "execution_strategy": {
                            "type": "string",
                            "enum": ["sequential", "parallel", "conditional"],
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "Explanation of routing decision",
                        },
                    },
                    "required": [
                        "task_type", "priority", "agents_needed",
                        "execution_strategy", "reasoning",
                    ],
                },
            },
            {
                "name": "route_to_agent",
                "description": "Route a task to a specific specialized agent and get result",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "agent_name": {
                            "type": "string",
                            "enum": [
                                "inventory", "order", "supplier",
                                "logistics", "demand_forecast", "anomaly_detection",
                            ],
                        },
                        "task_data": {
                            "type": "object",
                            "description": "Task-specific data to pass to the agent",
                        },
                        "action": {
                            "type": "string",
                            "description": "Specific action to perform",
                        },
                    },
                    "required": ["agent_name", "task_data", "action"],
                },
            },
            {
                "name": "aggregate_results",
                "description": "Aggregate results from multiple agents into a unified response",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "results": {
                            "type": "array",
                            "items": {"type": "object"},
                        },
                        "summary": {"type": "string"},
                        "action_items": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "alerts": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "type": {"type": "string"},
                                    "severity": {"type": "string"},
                                    "message": {"type": "string"},
                                },
                            },
                        },
                    },
                    "required": ["results", "summary"],
                },
            },
            {
                "name": "send_notification",
                "description": "Send a supply chain notification to Slack",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string"},
                        "severity": {
                            "type": "string",
                            "enum": ["info", "warning", "error", "critical"],
                        },
                        "category": {"type": "string"},
                    },
                    "required": ["message", "severity"],
                },
            },
        ]

    async def _handle_tool(self, tool_name: str, tool_input: Dict) -> Any:
        """Handle tool calls from Claude."""
        if tool_name == "analyze_task":
            # Just return the analysis (Claude did the work in the input)
            return {
                "status": "analysis_complete",
                "analysis": tool_input,
            }

        elif tool_name == "route_to_agent":
            agent_name = tool_input["agent_name"]
            task_data = tool_input.get("task_data", {})
            action = tool_input.get("action", "process")

            agent = self._get_agent(agent_name)
            if agent is None:
                return {"error": f"Agent '{agent_name}' not found"}

            try:
                logger.info(
                    "Routing to agent",
                    agent=agent_name,
                    action=action,
                )
                result = await agent.process({"action": action, **task_data})
                return {"agent": agent_name, "status": "success", "result": result}
            except Exception as e:
                logger.error("Agent routing failed", agent=agent_name, error=str(e))
                return {"agent": agent_name, "status": "error", "error": str(e)}

        elif tool_name == "aggregate_results":
            # Store aggregated results for return
            self._last_aggregation = tool_input
            return {"status": "aggregated", "summary": tool_input.get("summary")}

        elif tool_name == "send_notification":
            level_map = {
                "info": SlackLevel.INFO,
                "warning": SlackLevel.WARNING,
                "error": SlackLevel.ERROR,
                "critical": SlackLevel.CRITICAL,
            }
            level = level_map.get(tool_input.get("severity", "info"), SlackLevel.INFO)
            await self.slack.send(
                message=tool_input["message"],
                level=level,
                title=tool_input.get("category", "Supply Chain Alert"),
            )
            return {"status": "notification_sent"}

        return {"error": f"Unknown tool: {tool_name}"}

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main orchestration entry point.
        Analyzes the task and coordinates specialized agents.
        """
        task_id = str(uuid.uuid4())
        start_time = time.time()
        self._last_aggregation = None

        logger.info(
            "Orchestrator processing task",
            task_id=task_id,
            task_type=task.get("task_type", "unknown"),
        )

        # Notify start
        await self.notify_slack(
            f"Processing task `{task.get('task_type', 'unknown')}` (ID: `{task_id}`)",
            level=SlackLevel.INFO,
            title="Task Started",
        )

        try:
            # Build initial message for Claude
            user_message = f"""Analyze and orchestrate the following supply chain task:

Task Type: {task.get('task_type', 'unknown')}
Priority: {task.get('priority', 'medium')}
Data: {json.dumps(task.get('data', {}), default=str, indent=2)}

Please:
1. Use analyze_task to determine the routing strategy
2. Route to appropriate specialized agents using route_to_agent
3. Aggregate all results using aggregate_results
4. Send any important notifications using send_notification

Provide a comprehensive, actionable response."""

            messages = [{"role": "user", "content": user_message}]

            final_response, _ = await self.run_agentic_loop(
                initial_messages=messages,
                tool_handler=self._handle_tool,
                max_iterations=15,
            )

            elapsed_ms = int((time.time() - start_time) * 1000)

            result = {
                "task_id": task_id,
                "status": "completed",
                "task_type": task.get("task_type"),
                "response": final_response,
                "aggregated_data": self._last_aggregation,
                "execution_time_ms": elapsed_ms,
                "agents_invoked": list(self._agents.keys()),
            }

            # Notify completion
            await self.notify_slack(
                f"Task `{task_id}` completed in {elapsed_ms}ms",
                level=SlackLevel.SUCCESS,
                title="Task Completed",
            )

            logger.info(
                "Orchestrator task completed",
                task_id=task_id,
                elapsed_ms=elapsed_ms,
            )
            return result

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error("Orchestrator task failed", task_id=task_id, error=str(e))

            await self.notify_slack(
                f"Task `{task_id}` FAILED: {str(e)}",
                level=SlackLevel.ERROR,
                title="Task Failed",
            )

            return {
                "task_id": task_id,
                "status": "error",
                "error": str(e),
                "execution_time_ms": elapsed_ms,
            }
