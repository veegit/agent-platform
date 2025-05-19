"""
Router for the Agent Lifecycle Service.
"""

import logging
import uuid
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import ValidationError

from services.agent_lifecycle.models.agent import (
    Agent,
    AgentStatus,
    AgentConfig,
    CreateAgentRequest,
    UpdateAgentStatusRequest,
    UpdateAgentConfigRequest,
    AgentResponse,
    AgentListResponse,
    StatusResponse
)
from services.agent_lifecycle.repository import AgentRepository

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/agents",
    tags=["agents"]
)


async def get_repository() -> AgentRepository:
    """Get the agent repository.
    
    Returns:
        AgentRepository: The repository instance.
    """
    # In a real implementation, this would be a singleton or service instance
    # For the MVP, we create a new instance each time
    repository = AgentRepository()
    await repository.initialize()
    return repository


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(
    request: CreateAgentRequest,
    repository: AgentRepository = Depends(get_repository)
):
    """Create a new agent.
    
    Args:
        request: The create agent request.
        repository: The agent repository.
    
    Returns:
        AgentResponse: The created agent.
        
    Raises:
        HTTPException: If there's an error creating the agent.
    """
    try:
        # Generate a new agent ID if not provided
        if not request.config.agent_id:
            request.config.agent_id = str(uuid.uuid4())
        
        # Create the agent
        agent = Agent(
            agent_id=request.config.agent_id,
            status=AgentStatus.INACTIVE,  # New agents start as inactive
            config=request.config,
            created_by=request.created_by
        )
        
        # Store the agent
        await repository.create_agent(agent)
        
        # Return the agent
        return AgentResponse(
            agent_id=agent.agent_id,
            status=agent.status,
            config=agent.config,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
            created_by=agent.created_by
        )
    
    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid agent configuration: {str(e)}")
    
    except Exception as e:
        logger.error(f"Error creating agent: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create agent: {str(e)}")


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    repository: AgentRepository = Depends(get_repository)
):
    """Get an agent by ID.
    
    Args:
        agent_id: The ID of the agent to get.
        repository: The agent repository.
    
    Returns:
        AgentResponse: The agent.
        
    Raises:
        HTTPException: If the agent is not found.
    """
    agent = await repository.get_agent(agent_id)
    
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    return AgentResponse(
        agent_id=agent.agent_id,
        status=agent.status,
        config=agent.config,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
        created_by=agent.created_by
    )


@router.put("/{agent_id}/status", response_model=StatusResponse)
async def update_agent_status(
    agent_id: str,
    request: UpdateAgentStatusRequest,
    repository: AgentRepository = Depends(get_repository)
):
    """Update an agent's status.
    
    Args:
        agent_id: The ID of the agent to update.
        request: The update status request.
        repository: The agent repository.
    
    Returns:
        StatusResponse: The updated status.
        
    Raises:
        HTTPException: If the agent is not found or the update fails.
    """
    agent = await repository.get_agent(agent_id)
    
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    success = await repository.update_agent_status(agent_id, request.status)
    
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to update status of agent {agent_id}")
    
    return StatusResponse(
        agent_id=agent_id,
        status=request.status,
        message=f"Status of agent {agent_id} updated to {request.status.value}"
    )


@router.put("/{agent_id}/config", response_model=AgentResponse)
async def update_agent_config(
    agent_id: str,
    request: UpdateAgentConfigRequest,
    repository: AgentRepository = Depends(get_repository)
):
    """Update an agent's configuration.
    
    Args:
        agent_id: The ID of the agent to update.
        request: The update config request.
        repository: The agent repository.
    
    Returns:
        AgentResponse: The updated agent.
        
    Raises:
        HTTPException: If the agent is not found or the update fails.
    """
    agent = await repository.get_agent(agent_id)
    
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    # Ensure agent_id is preserved
    if request.config.agent_id != agent_id:
        request.config.agent_id = agent_id
    
    success = await repository.update_agent_config(agent_id, request.config)
    
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to update configuration of agent {agent_id}")
    
    # Get the updated agent
    updated_agent = await repository.get_agent(agent_id)
    
    return AgentResponse(
        agent_id=updated_agent.agent_id,
        status=updated_agent.status,
        config=updated_agent.config,
        created_at=updated_agent.created_at,
        updated_at=updated_agent.updated_at,
        created_by=updated_agent.created_by
    )


@router.get("", response_model=AgentListResponse)
async def list_agents(
    status: Optional[AgentStatus] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    repository: AgentRepository = Depends(get_repository)
):
    """List agents.
    
    Args:
        status: Optional status to filter by.
        skip: Number of agents to skip.
        limit: Maximum number of agents to return.
        repository: The agent repository.
    
    Returns:
        AgentListResponse: List of agents.
    """
    agents = await repository.list_agents(status, skip, limit)
    
    # Convert to API response model
    response_agents = []
    for agent in agents:
        response_agents.append(AgentResponse(
            agent_id=agent.agent_id,
            status=agent.status,
            config=agent.config,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
            created_by=agent.created_by
        ))
    
    return AgentListResponse(
        agents=response_agents,
        total=len(response_agents)  # For MVP, this is sufficient
    )


@router.delete("/{agent_id}", response_model=StatusResponse)
async def delete_agent(
    agent_id: str,
    repository: AgentRepository = Depends(get_repository)
):
    """Delete an agent.
    
    Args:
        agent_id: The ID of the agent to delete.
        repository: The agent repository.
    
    Returns:
        StatusResponse: The status response.
        
    Raises:
        HTTPException: If the agent is not found or the delete fails.
    """
    agent = await repository.get_agent(agent_id)
    
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    success = await repository.delete_agent(agent_id)
    
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to delete agent {agent_id}")
    
    return StatusResponse(
        agent_id=agent_id,
        status=AgentStatus.DELETED,
        message=f"Agent {agent_id} deleted successfully"
    )