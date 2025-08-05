"""
Agent configuration models for the Agentic Platform.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ReasoningModel(str, Enum):
    """LLM models for agent reasoning."""
    
    GEMINI_2_5_FLASH = "gemini-2.5-flash"
    GEMINI_1_5_PRO = "gemini-1.5-pro"
    GEMINI_1_5_FLASH = "gemini-1.5-flash"


class MemoryConfig(BaseModel):
    """Configuration for agent memory."""
    
    max_messages: int = Field(default=50, description="Maximum number of messages to keep in context")
    summarize_after: int = Field(default=20, description="Number of messages after which to create a summary")
    long_term_memory_enabled: bool = Field(default=True, description="Whether long-term memory is enabled")
    key_fact_extraction_enabled: bool = Field(default=True, description="Whether to extract key facts from conversations")


class AgentPersona(BaseModel):
    """Configuration for agent persona."""
    
    name: str = Field(..., description="Name of the agent")
    description: str = Field(..., description="Description of the agent")
    goals: List[str] = Field(default_factory=list, description="Goals of the agent")
    constraints: List[str] = Field(default_factory=list, description="Constraints on the agent's behavior")
    tone: str = Field(default="helpful and friendly", description="Tone of the agent's responses")
    system_prompt: str = Field(..., description="System prompt for the agent")


class AgentConfig(BaseModel):
    """Configuration for an agent."""

    agent_id: str = Field(..., description="Unique identifier for the agent")
    persona: AgentPersona = Field(..., description="Agent's persona")
    reasoning_model: ReasoningModel = Field(default=ReasoningModel.GEMINI_2_5_FLASH, description="LLM model for reasoning")
    skills: List[str] = Field(default_factory=list, description="Skills available to the agent")
    memory: MemoryConfig = Field(default_factory=MemoryConfig, description="Configuration for agent memory")
    is_supervisor: bool = Field(default=False, description="Whether this agent acts as a Supervisor")
    default_skill_params: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Default parameters for skills, keyed by skill_id"
    )
    additional_config: Dict[str, Any] = Field(default_factory=dict, description="Additional configuration options")
    
    class Config:
        """Configuration for the AgentConfig model."""
        
        json_schema_extra = {
            "example": {
                "agent_id": "123e4567-e89b-12d3-a456-426614174000",
                "persona": {
                    "name": "Research Assistant",
                    "description": "A helpful research assistant that can search the web and summarize information.",
                    "goals": ["Provide accurate information", "Assist with research tasks"],
                    "constraints": ["Do not make up facts", "Cite sources when possible"],
                    "tone": "professional and helpful",
                    "system_prompt": "You are a research assistant that helps users find and understand information. Always strive to provide factual, accurate responses and assist the user with their research needs."
                },
                "reasoning_model": "gemini-2.5-flash",
                "skills": ["web-search", "summarize-text", "ask-follow-up"],
                "memory": {
                    "max_messages": 50,
                    "summarize_after": 20,
                    "long_term_memory_enabled": True,
                    "key_fact_extraction_enabled": True
                },
                "default_skill_params": {
                    "web-search": {
                        "num_results": 5
                    }
                },
                "is_supervisor": False
            }
        }
