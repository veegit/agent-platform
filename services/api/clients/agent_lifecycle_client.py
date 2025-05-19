"""
Client for communicating with the Agent Lifecycle Service.
"""

import logging
import os
import json
import httpx
from datetime import datetime
from typing import Any, Dict, List, Optional

from services.api.models.agent import (
    AgentStatus,
    AgentSummary
)

logger = logging.getLogger(__name__)


class AgentLifecycleClient:
    """Client for communicating with the Agent Lifecycle Service."""
    
    def __init__(self, base_url: Optional[str] = None):
        """Initialize the agent lifecycle client.
        
        Args:
            base_url: The base URL of the agent lifecycle service. Defaults to environment variable.
        """
        self.base_url = base_url or os.environ.get("AGENT_LIFECYCLE_URL", "http://localhost:8001")
        logger.info(f"Initialized Agent Lifecycle client with base URL: {self.base_url}")
    
    async def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get an agent by ID.
        
        Args:
            agent_id: The ID of the agent to get.
            
        Returns:
            Optional[Dict[str, Any]]: The agent data, or None if not found.
        """
        try:
            logger.info(f"Getting agent {agent_id}")
            
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/agents/{agent_id}"
                print(f"Requesting URL: {url}")
                response = await client.get(
                    url,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    logger.warning(f"Agent {agent_id} not found")
                    return None
                else:
                    logger.error(f"Failed to get agent: {response.status_code} - {response.text}")
                    return None
                
        except Exception as e:
            logger.error(f"Error getting agent: {e}")
            return None
    
    async def list_agents(
        self, 
        status: Optional[AgentStatus] = None,
        skip: int = 0,
        limit: int = 100
    ) -> Dict[str, Any]:
        """List agents.
        
        Args:
            status: Optional status to filter by.
            skip: Number of agents to skip.
            limit: Maximum number of agents to return.
            
        Returns:
            Dict[str, Any]: The response data.
        """
        try:
            params = {
                "skip": skip,
                "limit": limit
            }
            
            if status:
                params["status"] = status.value
            
            logger.info(f"Listing agents with params: {params}")
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/agents",
                    params=params,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Failed to list agents: {response.status_code} - {response.text}")
                    return {
                        "agents": [],
                        "total": 0
                    }
                
        except Exception as e:
            logger.error(f"Error listing agents: {e}")
            return {
                "agents": [],
                "total": 0
            }
    
    async def get_agent_status(self, agent_id: str) -> Dict[str, Any]:
        """Get an agent's status.
        
        For the MVP, we'll use the get_agent method and extract the status,
        but in a production implementation, this might have more detailed status information.
        
        Args:
            agent_id: The ID of the agent.
            
        Returns:
            Dict[str, Any]: The agent status data.
        """
        agent_data = await self.get_agent(agent_id)
        
        if not agent_data:
            return {
                "agent_id": agent_id,
                "name": "Unknown",
                "status": AgentStatus.DELETED.value,
                "is_available": False,
                "active_conversations": 0,
                "last_active": None
            }
        
        # Extract the relevant fields
        status_str = agent_data.get("status", AgentStatus.INACTIVE.value)
        try:
            status = AgentStatus(status_str)
        except ValueError:
            status = AgentStatus.INACTIVE
        
        return {
            "agent_id": agent_id,
            "name": agent_data.get("config", {}).get("persona", {}).get("name", "Unknown"),
            "status": status.value,
            "is_available": status == AgentStatus.ACTIVE,
            "active_conversations": 0,  # For MVP, this is a placeholder
            "last_active": agent_data.get("updated_at")
        }