"""
Pydantic schemas for Agent orchestration API.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class AgentTaskType(str, Enum):
    ORDER_PROCESSING = "order_processing"
    INVENTORY_CHECK = "inventory_check"
    SUPPLIER_EVALUATION = "supplier_evaluation"
    LOGISTICS_OPTIMIZATION = "logistics_optimization"
    DEMAND_FORECASTING = "demand_forecasting"
    ANOMALY_DETECTION = "anomaly_detection"
    COMPREHENSIVE_ANALYSIS = "comprehensive_analysis"


class AgentTaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class OrchestrationRequest(BaseModel):
    task_type: AgentTaskType
    priority: AgentTaskPriority = AgentTaskPriority.MEDIUM
    data: Dict[str, Any] = {}
    timeout_seconds: int = Field(120, ge=10, le=600)
    notify_slack: bool = True
    callback_url: Optional[str] = None


class AgentTaskResult(BaseModel):
    task_id: str
    status: AgentTaskStatus
    agent_name: str
    task_type: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    agents_invoked: Optional[List[str]] = []
    execution_time_ms: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class OrchestrationResponse(BaseModel):
    task_id: str
    status: AgentTaskStatus
    message: str
    estimated_completion_seconds: int = 30


class AgentStatusResponse(BaseModel):
    name: str
    description: str
    model: str
    status: str
    total_requests: int
    success_rate: float
    avg_latency_ms: float


class AllAgentsStatusResponse(BaseModel):
    agents: List[AgentStatusResponse]
    total_agents: int
    healthy_agents: int
    last_updated: datetime
