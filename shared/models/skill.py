"""
Skill models for the Agentic Platform.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, validator
import uuid


class ParameterType(str, Enum):
    """Types of skill parameters."""
    
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


class SkillParameter(BaseModel):
    """Model for a skill parameter."""
    
    name: str = Field(..., description="Name of the parameter")
    type: ParameterType = Field(..., description="Type of the parameter")
    description: str = Field(..., description="Description of the parameter")
    required: bool = Field(default=True, description="Whether the parameter is required")
    default: Optional[Any] = Field(default=None, description="Default value for the parameter")
    enum: Optional[List[Any]] = Field(default=None, description="List of allowed values")


class ResponseFormat(BaseModel):
    """Model for the expected response format of a skill."""
    
    schema: Dict[str, Any] = Field(..., description="JSON schema for the response")
    description: str = Field(..., description="Description of the response format")


class Skill(BaseModel):
    """Model for a skill."""
    
    skill_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique identifier for the skill")
    name: str = Field(..., description="Human-readable name of the skill")
    description: str = Field(..., description="Description of what the skill does")
    parameters: List[SkillParameter] = Field(default_factory=list, description="Required and optional parameters")
    response_format: ResponseFormat = Field(..., description="Expected response structure")
    version: str = Field(default="1.0.0", description="Version of the skill")
    author: Optional[str] = Field(default=None, description="Author of the skill")
    tags: List[str] = Field(default_factory=list, description="Tags for the skill")
    
    class Config:
        """Configuration for the Skill model."""
        
        json_schema_extra = {
            "example": {
                "skill_id": "123e4567-e89b-12d3-a456-426614174000",
                "name": "Web Search",
                "description": "Search the web for information",
                "parameters": [
                    {
                        "name": "query",
                        "type": "string",
                        "description": "The search query",
                        "required": True
                    },
                    {
                        "name": "num_results",
                        "type": "integer",
                        "description": "Number of results to return",
                        "required": False,
                        "default": 5
                    }
                ],
                "response_format": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "results": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "title": {"type": "string"},
                                        "link": {"type": "string"},
                                        "snippet": {"type": "string"}
                                    }
                                }
                            }
                        }
                    },
                    "description": "List of search results with titles, links, and snippets"
                },
                "version": "1.0.0",
                "author": "Agentic Platform Team",
                "tags": ["search", "web"]
            }
        }


class SkillExecution(BaseModel):
    """Model for skill execution."""
    
    skill_id: str = Field(..., description="ID of the skill to execute")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Parameters for the skill execution")
    agent_id: Optional[str] = Field(default=None, description="ID of the agent executing the skill")
    conversation_id: Optional[str] = Field(default=None, description="ID of the conversation context")


class SkillResult(BaseModel):
    """Model for skill execution result."""
    
    result_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique identifier for the result")
    skill_id: str = Field(..., description="ID of the skill that was executed")
    status: str = Field(..., description="Status of the execution (success, error)")
    result: Union[Dict[str, Any], str] = Field(..., description="Result of the skill execution")
    error: Optional[str] = Field(default=None, description="Error message if execution failed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata about the execution")
    
    @validator("status")
    def status_must_be_valid(cls, v):
        """Validate that status is either success or error."""
        if v not in ["success", "error"]:
            raise ValueError(f"Status must be either 'success' or 'error', got '{v}'")
        return v