"""
Conversation models for the API service.
"""

from enum import Enum
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# Import AgentFlow for tracking agent execution paths
try:
    from shared.models.agent_flow import AgentFlow
except ImportError:
    # Fallback if import fails during development
    AgentFlow = None


class ConversationStatus(str, Enum):
    """Status of a conversation."""
    
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class MessageRole(str, Enum):
    """Role of a message sender."""
    
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class Message(BaseModel):
    """Model for a message in a conversation."""
    
    id: str = Field(..., description="Unique identifier for the message")
    role: MessageRole = Field(..., description="Role of the sender")
    content: str = Field(..., description="Content of the message")
    timestamp: datetime = Field(..., description="Timestamp of the message")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")
    agent_flow: Optional[Any] = Field(default=None, description="Agent execution flow data for this message")


class ConversationSummary(BaseModel):
    """Summary model for a conversation."""
    
    id: str = Field(..., description="Unique identifier for the conversation")
    agent_id: str = Field(..., description="ID of the agent")
    user_id: str = Field(..., description="ID of the user")
    title: Optional[str] = Field(default=None, description="Title of the conversation")
    last_message_timestamp: Optional[datetime] = Field(default=None, description="Timestamp of the last message")
    status: ConversationStatus = Field(..., description="Status of the conversation")
    message_count: int = Field(..., description="Number of messages in the conversation")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class Conversation(BaseModel):
    """Full model for a conversation with messages."""
    
    id: str = Field(..., description="Unique identifier for the conversation")
    agent_id: str = Field(..., description="ID of the agent")
    user_id: str = Field(..., description="ID of the user")
    title: Optional[str] = Field(default=None, description="Title of the conversation")
    status: ConversationStatus = Field(..., description="Status of the conversation")
    messages: List[Message] = Field(default_factory=list, description="Messages in the conversation")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")


# Request models for API
class StartConversationRequest(BaseModel):
    """Request model for starting a new conversation."""
    
    agent_id: str = Field(..., description="ID of the agent to start a conversation with")
    user_id: str = Field(..., description="ID of the user starting the conversation")
    initial_message: Optional[str] = Field(default=None, description="Optional initial message to send")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")


class SendMessageRequest(BaseModel):
    """Request model for sending a message in a conversation."""
    
    content: str = Field(..., description="Content of the message")
    user_id: str = Field(..., description="ID of the user sending the message")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")


# Response models for API
class ConversationResponse(BaseModel):
    """Response model for a conversation."""
    
    id: str = Field(..., description="Unique identifier for the conversation")
    agent_id: str = Field(..., description="ID of the agent")
    user_id: str = Field(..., description="ID of the user")
    title: Optional[str] = Field(default=None, description="Title of the conversation")
    status: ConversationStatus = Field(..., description="Status of the conversation")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    last_message: Optional[Message] = Field(default=None, description="Last message in the conversation")
    message_count: int = Field(..., description="Number of messages in the conversation")


class ConversationListResponse(BaseModel):
    """Response model for listing conversations."""
    
    conversations: List[ConversationSummary] = Field(..., description="List of conversations")
    total: int = Field(..., description="Total number of conversations")


class MessageResponse(BaseModel):
    """Response model for a message."""
    
    message: Message = Field(..., description="The message")
    conversation_id: str = Field(..., description="ID of the conversation")


class MessageListResponse(BaseModel):
    """Response model for listing messages."""
    
    messages: List[Message] = Field(..., description="List of messages")
    conversation_id: str = Field(..., description="ID of the conversation")
    total: int = Field(..., description="Total number of messages")