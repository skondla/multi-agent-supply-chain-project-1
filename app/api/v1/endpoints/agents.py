"""
Agents API endpoints - Orchestration and agent management.
"""
import uuid
from datetime import datetime
from typing import Optional
import structlog
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status

from app.core.security import get_current_user_id
from app.core.redis_client import CacheService
from app.schemas.agent import (
    OrchestrationRequest, OrchestrationResponse, AgentTaskResult,
    AgentTaskStatus, AllAgentsStatusResponse,
)

logger = structlog.get_logger()
router = APIRouter()

_task_cache = CacheService(prefix="agent_tasks", ttl=3600)
_agent_registry: dict = {}


def _get_orchestrator():
    from agents.orchestrator_agent import OrchestratorAgent
    if "orchestrator" not in _agent_registry:
        _agent_registry["orchestrator"] = OrchestratorAgent()
    return _agent_registry["orchestrator"]


async def _run_orchestration(task_id: str, request: OrchestrationRequest):
    """Background task for running orchestration."""
    orchestrator = _get_orchestrator()
    created_at = datetime.utcnow()

    # Update status to running
    await _task_cache.set(task_id, {
        "task_id": task_id,
        "status": "running",
        "agent_name": "OrchestratorAgent",
        "task_type": request.task_type,
        "created_at": created_at.isoformat(),
    })

    try:
        result = await orchestrator.process({
            "task_type": request.task_type,
            "priority": request.priority,
            "data": request.data,
        })

        await _task_cache.set(task_id, {
            "task_id": task_id,
            "status": "completed",
            "agent_name": "OrchestratorAgent",
            "task_type": request.task_type,
            "result": result,
            "agents_invoked": result.get("agents_invoked", []),
            "execution_time_ms": result.get("execution_time_ms"),
            "created_at": created_at.isoformat(),
            "completed_at": datetime.utcnow().isoformat(),
        })
    except Exception as e:
        logger.error("Orchestration failed", task_id=task_id, error=str(e))
        await _task_cache.set(task_id, {
            "task_id": task_id,
            "status": "failed",
            "agent_name": "OrchestratorAgent",
            "task_type": request.task_type,
            "error": str(e),
            "created_at": created_at.isoformat(),
            "completed_at": datetime.utcnow().isoformat(),
        })


@router.post("/orchestrate", response_model=OrchestrationResponse,
             status_code=status.HTTP_202_ACCEPTED,
             summary="Submit a task to the AI orchestrator")
async def orchestrate(
    request: OrchestrationRequest,
    background_tasks: BackgroundTasks,
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Submit a supply chain task to the multi-agent orchestrator.

    The orchestrator will analyze the task, route it to appropriate specialized
    agents (inventory, order, supplier, logistics, forecasting, anomaly detection),
    and return aggregated results.

    Results are available via GET /agents/tasks/{task_id}
    """
    task_id = str(uuid.uuid4())

    background_tasks.add_task(_run_orchestration, task_id, request)

    return OrchestrationResponse(
        task_id=task_id,
        status=AgentTaskStatus.PENDING,
        message=f"Task submitted for {request.task_type.value} with {request.priority.value} priority",
        estimated_completion_seconds=30,
    )


@router.get("/tasks/{task_id}", summary="Get task result")
async def get_task_result(
    task_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Get the result of a previously submitted agent task."""
    result = await _task_cache.get(task_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found or expired",
        )
    return result


@router.get("/status", response_model=AllAgentsStatusResponse, summary="Get all agent statuses")
async def get_all_agent_statuses(
    current_user_id: str = Depends(get_current_user_id),
):
    """Get health and performance status of all AI agents."""
    from agents.orchestrator_agent import OrchestratorAgent
    from agents.inventory_agent import InventoryAgent
    from agents.order_agent import OrderAgent
    from agents.supplier_agent import SupplierAgent
    from agents.logistics_agent import LogisticsAgent
    from agents.demand_forecast_agent import DemandForecastAgent
    from agents.anomaly_detection_agent import AnomalyDetectionAgent

    agent_classes = [
        OrchestratorAgent, InventoryAgent, OrderAgent,
        SupplierAgent, LogisticsAgent, DemandForecastAgent, AnomalyDetectionAgent,
    ]

    statuses = []
    for agent_class in agent_classes:
        # Get from registry or create temp instance for status
        name = agent_class.__name__
        agent = _agent_registry.get(name.lower().replace("agent", ""))
        if agent is None:
            agent = agent_class()
        statuses.append(agent.get_status())

    healthy = sum(1 for s in statuses if s["status"] == "active")

    return AllAgentsStatusResponse(
        agents=statuses,
        total_agents=len(statuses),
        healthy_agents=healthy,
        last_updated=datetime.utcnow(),
    )


@router.get("/{agent_name}/status", summary="Get specific agent status")
async def get_agent_status(
    agent_name: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Get status for a specific named agent."""
    valid_agents = ["orchestrator", "inventory", "order", "supplier", "logistics",
                    "demand_forecast", "anomaly_detection"]

    if agent_name not in valid_agents:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_name}' not found. Valid agents: {valid_agents}",
        )

    agent = _agent_registry.get(agent_name)
    if agent is None:
        return {"name": agent_name, "status": "idle", "message": "Agent not yet initialized"}

    return agent.get_status()
