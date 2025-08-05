"""
Agent models for the Agent Lifecycle Service.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

class AgentStatus(str, Enum):
    """Status of an agent."""
    
    ACTIVE = "active"
    INACTIVE = "inactive"
    PAUSED = "paused"
    DELETED = "deleted"


class AgentPersona(BaseModel):
    """Configuration for agent persona."""
    
    name: str = Field(..., description="Name of the agent")
    description: str = Field(..., description="Description of the agent")
    goals: List[str] = Field(default_factory=list, description="Goals of the agent")
    constraints: List[str] = Field(default_factory=list, description="Constraints on the agent's behavior")
    tone: str = Field(default="helpful and friendly", description="Tone of the agent's responses")
    system_prompt: str = Field(..., description="System prompt for the agent")


class LLMConfig(BaseModel):
    """Configuration for the LLM used by the agent."""
    
    model_name: str = Field(..., description="Name of the LLM model")
    temperature: float = Field(default=0.7, description="Temperature for the LLM")
    max_tokens: int = Field(default=2000, description="Maximum tokens for LLM responses")
    top_p: Optional[float] = Field(default=None, description="Top-p value for the LLM")
    frequency_penalty: Optional[float] = Field(default=None, description="Frequency penalty for the LLM")
    presence_penalty: Optional[float] = Field(default=None, description="Presence penalty for the LLM")
    provider: str = Field(default="gemini", description="Provider of the LLM")


class MemoryConfig(BaseModel):
    """Configuration for agent memory."""
    
    max_messages: int = Field(default=50, description="Maximum number of messages to keep in context")
    summarize_after: int = Field(default=20, description="Number of messages after which to create a summary")
    long_term_memory_enabled: bool = Field(default=True, description="Whether long-term memory is enabled")
    key_fact_extraction_enabled: bool = Field(default=True, description="Whether to extract key facts from conversations")


class AgentConfig(BaseModel):
    """Configuration for an agent."""

    agent_id: str = Field(..., description="Unique identifier for the agent")
    persona: AgentPersona = Field(..., description="Agent's persona")
    llm: LLMConfig = Field(..., description="LLM configuration")
    skills: List[str] = Field(default_factory=list, description="Skills available to the agent")
    memory: MemoryConfig = Field(default_factory=MemoryConfig, description="Configuration for agent memory")
    is_supervisor: bool = Field(default=False, description="Whether this agent acts as a Supervisor")
    default_skill_params: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Default parameters for skills, keyed by skill_id"
    )
    additional_config: Dict[str, Any] = Field(default_factory=dict, description="Additional configuration options")


class Agent(BaseModel):
    """Full agent model with metadata."""
    
    agent_id: str = Field(..., description="Unique identifier for the agent")
    status: AgentStatus = Field(default=AgentStatus.INACTIVE, description="Status of the agent")
    config: AgentConfig = Field(..., description="Agent configuration")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")
    created_by: Optional[str] = Field(default=None, description="User who created the agent")
    usage_stats: Dict[str, Any] = Field(default_factory=dict, description="Usage statistics")


# Request models for API
class CreateAgentRequest(BaseModel):
    """Request model for creating a new agent."""

    config: AgentConfig = Field(..., description="Agent configuration")
    created_by: Optional[str] = Field(default=None, description="User who created the agent")
    domain: Optional[str] = Field(default=None, description="Domain name for delegation")
    keywords: List[str] = Field(default_factory=list, description="Example keywords for this domain")


class UpdateAgentStatusRequest(BaseModel):
    """Request model for updating an agent's status."""
    
    status: AgentStatus = Field(..., description="New status for the agent")


class UpdateAgentConfigRequest(BaseModel):
    """Request model for updating an agent's configuration."""
    
    config: AgentConfig = Field(..., description="Updated agent configuration")


# Response models for API
class AgentResponse(BaseModel):
    """Response model for agent data."""
    
    agent_id: str = Field(..., description="Unique identifier for the agent")
    status: AgentStatus = Field(..., description="Status of the agent")
    config: AgentConfig = Field(..., description="Agent configuration")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    created_by: Optional[str] = Field(default=None, description="User who created the agent")


class AgentListResponse(BaseModel):
    """Response model for listing agents."""
    
    agents: List[AgentResponse] = Field(..., description="List of agents")
    total: int = Field(..., description="Total number of agents")


class StatusResponse(BaseModel):
    """Response model for status updates."""

    agent_id: str = Field(..., description="Unique identifier for the agent")
    status: AgentStatus = Field(..., description="Status of the agent")
    message: str = Field(..., description="Status message")
