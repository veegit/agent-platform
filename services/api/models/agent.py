"""
Agent models for the API service.
"""

from enum import Enum
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AgentStatus(str, Enum):
    """Status of an agent."""
    
    ACTIVE = "active"
    INACTIVE = "inactive"
    PAUSED = "paused"
    DELETED = "deleted"


class AgentSummary(BaseModel):
    """Summary model for an agent."""
    
    agent_id: str = Field(..., description="Unique identifier for the agent")
    name: str = Field(..., description="Name of the agent")
    description: str = Field(..., description="Description of the agent")
    status: AgentStatus = Field(..., description="Status of the agent")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class AgentListResponse(BaseModel):
    """Response model for listing agents."""
    
    agents: List[AgentSummary] = Field(..., description="List of agents")
    total: int = Field(..., description="Total number of agents")


class AgentStatusResponse(BaseModel):
    """Response model for agent status."""
    
    agent_id: str = Field(..., description="Unique identifier for the agent")
    name: str = Field(..., description="Name of the agent")
    status: AgentStatus = Field(..., description="Status of the agent")
    is_available: bool = Field(..., description="Whether the agent is available for conversations")
    active_conversations: int = Field(..., description="Number of active conversations")
    last_active: Optional[datetime] = Field(default=None, description="Timestamp of last activity")