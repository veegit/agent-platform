"""
Agent state models for the Agentic Platform.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from shared.models.skill import SkillExecution, SkillResult


class MessageRole(str, Enum):
    """Roles for messages in a conversation."""
    
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class Message(BaseModel):
    """Model for a message in the agent's conversation."""
    
    id: str = Field(..., description="Unique identifier for the message")
    role: MessageRole = Field(..., description="Role of the sender")
    content: str = Field(..., description="Content of the message")
    timestamp: datetime = Field(default_factory=datetime.now, description="Timestamp of the message")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    agent_flow: Optional[Dict[str, Any]] = Field(default=None, description="Agent execution flow data for this message")


class Memory(BaseModel):
    """Model for agent memory."""
    
    long_term: Dict[str, Any] = Field(default_factory=dict, description="Long-term memory")
    working: Dict[str, Any] = Field(default_factory=dict, description="Working memory for current reasoning")
    conversation_summary: Optional[str] = Field(None, description="Summary of the conversation so far")
    key_facts: List[str] = Field(default_factory=list, description="Key facts to remember")
    

class AgentState(BaseModel):
    """Model for the agent's state in the LangGraph state machine."""
    
    # Core conversation and context
    agent_id: str = Field(..., description="ID of the agent")
    conversation_id: str = Field(..., description="ID of the current conversation")
    user_id: str = Field(..., description="ID of the user")
    messages: List[Message] = Field(default_factory=list, description="Messages in the conversation")
    
    # Memory (conversation context)
    memory: Memory = Field(default_factory=Memory, description="Agent's memory")
    
    # Current execution state
    current_node: Optional[str] = Field(None, description="Current node in the state graph")
    current_skill: Optional[SkillExecution] = Field(None, description="Current skill being executed")
    skill_results: List[SkillResult] = Field(default_factory=list, description="Results of skill executions")
    
    # Agent thinking and reasoning
    thought_process: List[str] = Field(default_factory=list, description="Agent's thought process")
    observations: List[str] = Field(default_factory=list, description="Agent's observations")
    plan: List[str] = Field(default_factory=list, description="Agent's plan")
    
    # Tracking information
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")
    error: Optional[str] = Field(None, description="Error message if any")
    
    class Config:
        """Configuration for the AgentState model."""
        
        arbitrary_types_allowed = True


class AgentOutput(BaseModel):
    """Model for the agent's output."""
    
    message: Message = Field(..., description="The message to send to the user")
    state: AgentState = Field(..., description="The updated agent state")


class SkillChoice(BaseModel):
    """Model for a skill choice by the agent."""
    
    skill_id: str = Field(..., description="ID of the skill to execute")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Parameters for the skill execution")
    reason: str = Field(..., description="Reason for choosing this skill")


class ReasoningOutput(BaseModel):
    """Output from the reasoning node."""
    
    thoughts: str = Field(..., description="Agent's thoughts and reasoning")
    skill_to_use: Optional[SkillChoice] = Field(None, description="Skill the agent wants to use, if any")
    response_to_user: Optional[str] = Field(None, description="Direct response to user, if not using a skill")
    should_respond_directly: bool = Field(False, description="Whether to respond directly to the user")
    state: AgentState = Field(..., description="The updated agent state")


class SkillExecutionOutput(BaseModel):
    """Output from the skill execution node."""
    
    skill_result: SkillResult = Field(..., description="Result of the skill execution")
    state: AgentState = Field(..., description="The updated agent state")


class ResponseFormulationOutput(BaseModel):
    """Output from the response formulation node."""
    
    message: Message = Field(..., description="Formulated response to the user")
    state: AgentState = Field(..., description="The updated agent state")