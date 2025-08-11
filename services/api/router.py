"""
API router for the Agentic Platform.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Query, Path

from services.api.models.conversation import (
    StartConversationRequest,
    SendMessageRequest,
    ConversationResponse,
    ConversationListResponse,
    MessageResponse,
    MessageListResponse,
    ConversationStatus,
    ConversationSummary,
    Message,
    MessageRole
)
from services.api.models.agent import (
    AgentStatusResponse,
    AgentListResponse,
    AgentStatus,
    AgentSummary
)
from services.api.conversations import ConversationService
from services.api.clients.agent_lifecycle_client import AgentLifecycleClient

logger = logging.getLogger(__name__)

# Create the router
router = APIRouter()


# Dependencies
async def get_conversation_service() -> ConversationService:
    """Get the conversation service."""
    service = ConversationService()
    await service.initialize()
    return service

async def get_agent_lifecycle_client() -> AgentLifecycleClient:
    """Get the agent lifecycle client."""
    return AgentLifecycleClient()


# Conversation endpoints
@router.post("/conversations", response_model=ConversationResponse)
async def start_conversation(
    request: StartConversationRequest,
    conversation_service: ConversationService = Depends(get_conversation_service)
):
    """Start a new conversation with an agent.
    
    Args:
        request: The start conversation request.
        conversation_service: The conversation service.
        
    Returns:
        ConversationResponse: The conversation response.
        
    Raises:
        HTTPException: If there's an error starting the conversation.
    """
    response = await conversation_service.start_conversation(
        agent_id=request.agent_id,
        user_id=request.user_id,
        initial_message=request.initial_message,
        metadata=request.metadata
    )
    
    if "error" in response:
        raise HTTPException(status_code=400, detail=response["error"])
    
    # Convert to response model
    last_message = None
    messages = response.get("messages", [])
    if messages:
        last_message_data = messages[-1]
        timestamp = last_message_data.get("timestamp")
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp)
            except ValueError:
                timestamp = datetime.now()
                
        last_message = Message(
            id=last_message_data.get("id", ""),
            role=last_message_data.get("role", MessageRole.AGENT),
            content=last_message_data.get("content", ""),
            timestamp=timestamp,
            metadata=last_message_data.get("metadata")
        )
    
    try:
        return ConversationResponse(
            id=response.get("id"),
            agent_id=response.get("agent_id"),
            user_id=response.get("user_id"),
            title=response.get("metadata", {}).get("title"),
            status=ConversationStatus(response.get("status")),
            created_at=datetime.fromisoformat(response.get("created_at")),
            updated_at=datetime.fromisoformat(response.get("updated_at")),
            last_message=last_message,
            message_count=len(messages)
        )
    except Exception as e:
        logger.error(f"Error creating response: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/conversations/{conversation_id}/messages", response_model=MessageResponse)
async def send_message(
    conversation_id: str = Path(..., description="ID of the conversation"),
    request: SendMessageRequest = None,
    conversation_service: ConversationService = Depends(get_conversation_service)
):
    """Send a message in a conversation.
    
    Args:
        conversation_id: The ID of the conversation.
        request: The send message request.
        conversation_service: The conversation service.
        
    Returns:
        MessageResponse: The message response.
        
    Raises:
        HTTPException: If there's an error sending the message.
    """
    response = await conversation_service.send_message(
        conversation_id=conversation_id,
        content=request.content,
        user_id=request.user_id,
        metadata=request.metadata
    )
    
    if "error" in response:
        raise HTTPException(status_code=400, detail=response["error"])
    
    # Extract the agent's message
    agent_message_data = response.get("agent_message", {})
    
    # Debug: Log agent flow data
    agent_flow_data = agent_message_data.get("agent_flow")
    logger.info(f"Agent flow data in API router: {agent_flow_data}")
    timestamp = agent_message_data.get("timestamp")
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp)
        except ValueError:
            timestamp = datetime.now()
            
    agent_message = Message(
        id=agent_message_data.get("id", ""),
        role=agent_message_data.get("role", MessageRole.AGENT),
        content=agent_message_data.get("content", ""),
        timestamp=timestamp,
        metadata=agent_message_data.get("metadata"),
        agent_flow=agent_message_data.get("agent_flow")
    )
    
    return MessageResponse(
        message=agent_message,
        conversation_id=conversation_id
    )


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
    status: Optional[ConversationStatus] = Query(None, description="Filter by status"),
    skip: int = Query(0, ge=0, description="Number of conversations to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of conversations to return"),
    conversation_service: ConversationService = Depends(get_conversation_service)
):
    """List conversations.
    
    Args:
        user_id: Optional user ID to filter by.
        agent_id: Optional agent ID to filter by.
        status: Optional status to filter by.
        skip: Number of conversations to skip.
        limit: Maximum number of conversations to return.
        conversation_service: The conversation service.
        
    Returns:
        ConversationListResponse: The list of conversations.
    """
    response = await conversation_service.list_conversations(
        user_id=user_id,
        agent_id=agent_id,
        status=status,
        skip=skip,
        limit=limit
    )
    
    # Convert to response model
    conversations = []
    for conv_data in response.get("conversations", []):
        last_message_timestamp = conv_data.get("last_message_timestamp")
        if isinstance(last_message_timestamp, str):
            try:
                last_message_timestamp = datetime.fromisoformat(last_message_timestamp)
            except ValueError:
                last_message_timestamp = None
                
        created_at = conv_data.get("created_at")
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at)
            except ValueError:
                created_at = datetime.now()
                
        updated_at = conv_data.get("updated_at")
        if isinstance(updated_at, str):
            try:
                updated_at = datetime.fromisoformat(updated_at)
            except ValueError:
                updated_at = datetime.now()
                
        conversations.append(ConversationSummary(
            id=conv_data.get("id"),
            agent_id=conv_data.get("agent_id"),
            user_id=conv_data.get("user_id"),
            title=conv_data.get("title"),
            last_message_timestamp=last_message_timestamp,
            status=ConversationStatus(conv_data.get("status")),
            message_count=conv_data.get("message_count", 0),
            created_at=created_at,
            updated_at=updated_at
        ))
    
    return ConversationListResponse(
        conversations=conversations,
        total=response.get("total", 0)
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str = Path(..., description="ID of the conversation"),
    conversation_service: ConversationService = Depends(get_conversation_service)
):
    """Get a conversation by ID.
    
    Args:
        conversation_id: The ID of the conversation.
        conversation_service: The conversation service.
        
    Returns:
        ConversationResponse: The conversation.
        
    Raises:
        HTTPException: If the conversation is not found.
    """
    response = await conversation_service.get_conversation(conversation_id)
    
    if not response:
        raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")
    
    # Convert to response model
    last_message = None
    messages = response.get("messages", [])
    if messages:
        last_message_data = messages[-1]
        timestamp = last_message_data.get("timestamp")
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp)
            except ValueError:
                timestamp = datetime.now()
                
        last_message = Message(
            id=last_message_data.get("id", ""),
            role=last_message_data.get("role", MessageRole.AGENT),
            content=last_message_data.get("content", ""),
            timestamp=timestamp,
            metadata=last_message_data.get("metadata")
        )
    
    created_at = response.get("created_at")
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at)
        except ValueError:
            created_at = datetime.now()
            
    updated_at = response.get("updated_at")
    if isinstance(updated_at, str):
        try:
            updated_at = datetime.fromisoformat(updated_at)
        except ValueError:
            updated_at = datetime.now()
    
    return ConversationResponse(
        id=response.get("id"),
        agent_id=response.get("agent_id"),
        user_id=response.get("user_id"),
        title=response.get("metadata", {}).get("title"),
        status=ConversationStatus(response.get("status")),
        created_at=created_at,
        updated_at=updated_at,
        last_message=last_message,
        message_count=len(messages)
    )


@router.get("/conversations/{conversation_id}/messages", response_model=MessageListResponse)
async def get_conversation_messages(
    conversation_id: str = Path(..., description="ID of the conversation"),
    skip: int = Query(0, ge=0, description="Number of messages to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of messages to return"),
    conversation_service: ConversationService = Depends(get_conversation_service)
):
    """Get messages from a conversation.
    
    Args:
        conversation_id: The ID of the conversation.
        skip: Number of messages to skip.
        limit: Maximum number of messages to return.
        conversation_service: The conversation service.
        
    Returns:
        MessageListResponse: The list of messages.
        
    Raises:
        HTTPException: If the conversation is not found.
    """
    response = await conversation_service.get_conversation_messages(
        conversation_id=conversation_id,
        skip=skip,
        limit=limit
    )
    
    if "error" in response:
        raise HTTPException(status_code=404, detail=response["error"])
    
    # Convert to response model
    messages = []
    for msg_data in response.get("messages", []):
        timestamp = msg_data.get("timestamp")
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp)
            except ValueError:
                timestamp = datetime.now()
                
        messages.append(Message(
            id=msg_data.get("id", ""),
            role=msg_data.get("role", MessageRole.USER),
            content=msg_data.get("content", ""),
            timestamp=timestamp,
            metadata=msg_data.get("metadata")
        ))
    
    return MessageListResponse(
        messages=messages,
        conversation_id=conversation_id,
        total=response.get("total", 0)
    )


# Agent endpoints
@router.get("/agents", response_model=AgentListResponse)
async def list_agents(
    status: Optional[AgentStatus] = Query(None, description="Filter by status"),
    skip: int = Query(0, ge=0, description="Number of agents to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of agents to return"),
    agent_lifecycle_client: AgentLifecycleClient = Depends(get_agent_lifecycle_client)
):
    """List agents.
    
    Args:
        status: Optional status to filter by.
        skip: Number of agents to skip.
        limit: Maximum number of agents to return.
        agent_lifecycle_client: The agent lifecycle client.
        
    Returns:
        AgentListResponse: The list of agents.
    """
    response = await agent_lifecycle_client.list_agents(
        status=status,
        skip=skip,
        limit=limit
    )
    
    # Convert to response model
    agents = []
    for agent_data in response.get("agents", []):
        created_at = agent_data.get("created_at")
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at)
            except ValueError:
                created_at = datetime.now()
                
        updated_at = agent_data.get("updated_at")
        if isinstance(updated_at, str):
            try:
                updated_at = datetime.fromisoformat(updated_at)
            except ValueError:
                updated_at = datetime.now()
                
        agents.append(AgentSummary(
            agent_id=agent_data.get("agent_id"),
            name=agent_data.get("config", {}).get("persona", {}).get("name", "Unknown"),
            description=agent_data.get("config", {}).get("persona", {}).get("description", ""),
            status=AgentStatus(agent_data.get("status")),
            created_at=created_at,
            updated_at=updated_at
        ))
    
    return AgentListResponse(
        agents=agents,
        total=response.get("total", 0)
    )


@router.get("/agents/{agent_id}/status", response_model=AgentStatusResponse)
async def get_agent_status(
    agent_id: str = Path(..., description="ID of the agent"),
    agent_lifecycle_client: AgentLifecycleClient = Depends(get_agent_lifecycle_client)
):
    """Get an agent's status.
    
    Args:
        agent_id: The ID of the agent.
        agent_lifecycle_client: The agent lifecycle client.
        
    Returns:
        AgentStatusResponse: The agent status.
        
    Raises:
        HTTPException: If the agent is not found.
    """
    response = await agent_lifecycle_client.get_agent_status(agent_id)
    
    if not response:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    last_active = response.get("last_active")
    if isinstance(last_active, str):
        try:
            last_active = datetime.fromisoformat(last_active)
        except ValueError:
            last_active = None
    
    return AgentStatusResponse(
        agent_id=response.get("agent_id"),
        name=response.get("name"),
        status=AgentStatus(response.get("status")),
        is_available=response.get("is_available", False),
        active_conversations=response.get("active_conversations", 0),
        last_active=last_active
    )

@router.get("/health")
async def health():
    return {"status": "ok"}