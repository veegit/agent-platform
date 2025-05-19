"""
Repository for agent management in the Agent Lifecycle Service.
"""

import logging
import json
from datetime import datetime
from typing import Dict, List, Optional, Any

from shared.utils.redis_manager import RedisManager
from shared.utils.redis_agent_store import RedisAgentStore
from services.agent_lifecycle.models.agent import Agent, AgentStatus, AgentConfig

logger = logging.getLogger(__name__)


class AgentRepository:
    """Repository for agent management."""
    
    # Redis key prefixes
    AGENT_KEY_PREFIX = "agent:"
    AGENT_CONFIG_KEY_PREFIX = "agent:config:"
    AGENT_STATUS_KEY_PREFIX = "agent:status:"
    ALL_AGENTS_KEY = "agents:all"
    
    def __init__(self, redis_manager: Optional[RedisManager] = None):
        """Initialize the agent repository.
        
        Args:
            redis_manager: Optional Redis manager. A new one will be created if not provided.
        """
        self.redis_manager = redis_manager or RedisManager()
        self.agent_store = None
    
    async def initialize(self) -> None:
        """Initialize the repository."""
        if not self.redis_manager.agents:
            await self.redis_manager.connect()
            
        self.agent_store = self.redis_manager.agents
        logger.info("Agent repository initialized")
    
    async def create_agent(self, agent: Agent) -> str:
        """Create a new agent.
        
        Args:
            agent: The agent to create.
            
        Returns:
            str: The agent ID.
        """
        if not self.agent_store:
            await self.initialize()
        
        try:
            # Create agent data for storage
            agent_data = {
                "agent_id": agent.agent_id,
                "name": agent.config.persona.name,
                "description": agent.config.persona.description,
                "status": agent.status.value
            }
            
            # Store agent config separately for better organization
            config_data = agent.config.dict()
            
            # Create Redis-compatible agent data
            redis_agent_data = {
                "agent_id": agent.agent_id,
                "name": agent.config.persona.name,
                "description": agent.config.persona.description,
                "status": agent.status.value,
                "skills": agent.config.skills,
                "config": config_data
            }
            
            # Store the agent
            await self.agent_store.store_agent(redis_agent_data)
            
            # Store agent's full data
            agent_key = f"{self.AGENT_KEY_PREFIX}{agent.agent_id}"
            
            # Update timestamps
            agent.created_at = datetime.now()
            agent.updated_at = datetime.now()
            
            # Store the full agent data
            await self.redis_manager.redis_client.set_value(agent_key, agent.dict())
            
            logger.info(f"Created agent {agent.agent_id}")
            return agent.agent_id
            
        except Exception as e:
            logger.error(f"Failed to create agent: {e}")
            raise
    
    async def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Get an agent by ID.
        
        Args:
            agent_id: The ID of the agent to get.
            
        Returns:
            Optional[Agent]: The agent, or None if not found.
        """
        if not self.agent_store:
            await self.initialize()
        
        try:
            # Try to get full agent data first
            agent_key = f"{self.AGENT_KEY_PREFIX}{agent_id}"
            agent_data = await self.redis_manager.redis_client.get_value(agent_key)
            
            if agent_data:
                # Return the full agent data
                return Agent(**agent_data)
            
            # Fall back to agent store if full data not found
            basic_agent_data = await self.agent_store.get_agent(agent_id)
            
            if not basic_agent_data:
                logger.warning(f"Agent {agent_id} not found")
                return None
            
            # Convert to Agent model
            status_str = basic_agent_data.get("status", "inactive")
            try:
                status = AgentStatus(status_str)
            except ValueError:
                status = AgentStatus.INACTIVE
                logger.warning(f"Invalid status '{status_str}' for agent {agent_id}, defaulting to INACTIVE")
            
            config = AgentConfig(**basic_agent_data.get("config", {}))
            
            # Create Agent object
            agent = Agent(
                agent_id=agent_id,
                status=status,
                config=config,
                created_at=datetime.now(),  # Use current time as fallback
                updated_at=datetime.now()
            )
            
            # Save the full agent data for future use
            await self.redis_manager.redis_client.set_value(agent_key, agent.dict())
            
            return agent
            
        except Exception as e:
            logger.error(f"Failed to get agent {agent_id}: {e}")
            return None
    
    async def update_agent_status(self, agent_id: str, status: AgentStatus) -> bool:
        """Update an agent's status.
        
        Args:
            agent_id: The ID of the agent to update.
            status: The new status.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        if not self.agent_store:
            await self.initialize()
        
        try:
            # Get the agent
            agent = await self.get_agent(agent_id)
            
            if not agent:
                logger.warning(f"Agent {agent_id} not found")
                return False
            
            # Update the status
            agent.status = status
            agent.updated_at = datetime.now()
            
            # Store the updated agent data
            agent_key = f"{self.AGENT_KEY_PREFIX}{agent_id}"
            await self.redis_manager.redis_client.set_value(agent_key, agent.dict())
            
            # Update the status in the agent store
            success = await self.agent_store.update_agent_status(agent_id, status.value)
            
            # Store the status history
            status_key = f"{self.AGENT_STATUS_KEY_PREFIX}{agent_id}"
            await self.redis_manager.redis_client.add_to_list(status_key, {
                "status": status.value,
                "timestamp": datetime.now().isoformat()
            })
            
            logger.info(f"Updated status of agent {agent_id} to {status.value}")
            return success
            
        except Exception as e:
            logger.error(f"Failed to update status of agent {agent_id}: {e}")
            return False
    
    async def update_agent_config(self, agent_id: str, config: AgentConfig) -> bool:
        """Update an agent's configuration.
        
        Args:
            agent_id: The ID of the agent to update.
            config: The new configuration.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        if not self.agent_store:
            await self.initialize()
        
        try:
            # Get the agent
            agent = await self.get_agent(agent_id)
            
            if not agent:
                logger.warning(f"Agent {agent_id} not found")
                return False
            
            # Update the configuration
            agent.config = config
            agent.updated_at = datetime.now()
            
            # Store the updated agent data
            agent_key = f"{self.AGENT_KEY_PREFIX}{agent_id}"
            await self.redis_manager.redis_client.set_value(agent_key, agent.dict())
            
            # Update the configuration in the agent store
            redis_agent_data = {
                "agent_id": agent_id,
                "name": config.persona.name,
                "description": config.persona.description,
                "status": agent.status.value,
                "skills": config.skills,
                "config": config.dict()
            }
            
            await self.agent_store.store_agent(redis_agent_data)
            
            logger.info(f"Updated configuration of agent {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update configuration of agent {agent_id}: {e}")
            return False
    
    async def list_agents(
        self, 
        status_filter: Optional[AgentStatus] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Agent]:
        """List agents.
        
        Args:
            status_filter: Optional status to filter by.
            skip: Number of agents to skip.
            limit: Maximum number of agents to return.
            
        Returns:
            List[Agent]: List of agents.
        """
        if not self.agent_store:
            await self.initialize()
        
        try:
            # Get all agent IDs
            agent_ids = await self.agent_store.list_agents()
            
            agents = []
            
            # Get each agent
            for agent_id in agent_ids:
                try:
                    agent = await self.get_agent(agent_id)
                    
                    if agent and (not status_filter or agent.status == status_filter):
                        agents.append(agent)
                except Exception as e:
                    logger.error(f"Error getting agent {agent_id}: {e}")
                    continue
            
            # Sort by updated_at (newest first)
            agents.sort(key=lambda a: a.updated_at, reverse=True)
            
            # Apply pagination
            return agents[skip:skip+limit]
            
        except Exception as e:
            logger.error(f"Failed to list agents: {e}")
            return []
    
    async def delete_agent(self, agent_id: str) -> bool:
        """Delete an agent.
        
        Args:
            agent_id: The ID of the agent to delete.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        if not self.agent_store:
            await self.initialize()
        
        try:
            # Get the agent
            agent = await self.get_agent(agent_id)
            
            if not agent:
                logger.warning(f"Agent {agent_id} not found")
                return False
            
            # Update the status to DELETED
            agent.status = AgentStatus.DELETED
            agent.updated_at = datetime.now()
            
            # Store the updated agent data
            agent_key = f"{self.AGENT_KEY_PREFIX}{agent_id}"
            await self.redis_manager.redis_client.set_value(agent_key, agent.dict())
            
            # Update the status in the agent store
            success = await self.agent_store.update_agent_status(agent_id, AgentStatus.DELETED.value)
            
            # For the MVP, we don't actually delete the agent data, just mark it as deleted
            # In a production implementation, we might have a separate cleanup process
            
            logger.info(f"Deleted agent {agent_id}")
            return success
            
        except Exception as e:
            logger.error(f"Failed to delete agent {agent_id}: {e}")
            return False