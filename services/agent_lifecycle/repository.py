"""
Repository for agent management in the Agent Lifecycle Service.
"""

import logging
import json
from datetime import datetime
from typing import Dict, List, Optional, Any

from shared.utils.redis_manager import RedisManager
from shared.utils.redis_agent_store import RedisAgentStore
from shared.utils.json_utils import DateTimeEncoder
from services.agent_lifecycle.models.agent import Agent, AgentStatus, AgentConfig, AgentPersona, LLMConfig

logger = logging.getLogger(__name__)


class AgentRepository:
    """Repository for agent management."""
    
    # Redis key prefixes
    AGENT_KEY_PREFIX = "agent:"
    AGENT_CONFIG_KEY_PREFIX = "agent:config:"
    AGENT_STATUS_KEY_PREFIX = "agent:status:"
    AGENT_SKILLS_KEY_PREFIX = "agent:skills:"
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
            await self.redis_manager.redis_client.set_value(agent_key, json.dumps(agent.dict(), cls=DateTimeEncoder))
            
            logger.info(f"Created agent {agent.agent_id}")
            return agent.agent_id
            
        except Exception as e:
            logger.error(f"Failed to create agent: {e}")
            raise
    
    def _normalize_datetime_fields(self, data: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        """Helper to normalize datetime fields in agent data.
        
        Args:
            data: The agent data dictionary
            agent_id: The agent ID (for logging)
            
        Returns:
            Dict[str, Any]: The normalized data dictionary
        """
        try:
            if 'created_at' in data and data['created_at']:
                data['created_at'] = datetime.fromisoformat(data['created_at'])
            else:
                data['created_at'] = datetime.now()
                
            if 'updated_at' in data and data['updated_at']:
                data['updated_at'] = datetime.fromisoformat(data['updated_at'])
            else:
                data['updated_at'] = datetime.now()
        except Exception as e:
            logger.warning(f"Error parsing datetime fields for agent {agent_id}: {e}")
            data['created_at'] = datetime.now()
            data['updated_at'] = datetime.now()
            
        return data
    
    def _create_default_config(self, agent_id: str, skills: List[str] = None) -> AgentConfig:
        """Create a default agent configuration.
        
        Args:
            agent_id: The agent ID
            skills: Optional list of skills
            
        Returns:
            AgentConfig: A default configuration
        """
        return AgentConfig(
            agent_id=agent_id,
            persona=AgentPersona(
                name=f"Agent {agent_id}",
                description="Default agent",
                system_prompt="You are a helpful assistant."
            ),
            llm=LLMConfig(
                model_name="llama3-70b-8192"
            ),
            skills=skills or []
        )
        
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
            # Try to get full agent data first from Redis
            agent_key = f"{self.AGENT_KEY_PREFIX}{agent_id}"
            raw_agent_data = await self.redis_manager.redis_client.redis.get(agent_key)
            
            # Attempt to build agent from Redis data
            if raw_agent_data:
                try:
                    # Parse agent data
                    agent_data = json.loads(raw_agent_data)
                    
                    # Ensure required fields are present
                    if not agent_data.get('agent_id'):
                        agent_data['agent_id'] = agent_id
                    
                    # Handle datetime fields
                    agent_data = self._normalize_datetime_fields(agent_data, agent_id)
                    
                    # Create Agent object
                    logger.info(f"Creating Agent from Redis data with keys: {list(agent_data.keys())}")
                    return Agent(**agent_data)
                except Exception as e:
                    logger.warning(f"Error parsing Redis data for agent {agent_id}: {e}")
            
            # Fall back to agent store if Redis data not found or corrupted
            logger.info(f"Falling back to agent store for agent {agent_id}")
            basic_agent_data = await self.agent_store.get_agent(agent_id)
            
            if not basic_agent_data:
                logger.warning(f"Agent {agent_id} not found in agent store")
                return None
            
            # Log the agent data we got from the store
            logger.info(f"Got basic agent data from store: {list(basic_agent_data.keys())}")
            
            # Extract agent status
            status_str = basic_agent_data.get("status", "inactive")
            try:
                status = AgentStatus(status_str)
            except ValueError:
                status = AgentStatus.INACTIVE
                logger.warning(f"Invalid status '{status_str}' for agent {agent_id}, defaulting to INACTIVE")
            
            # Get skills if available
            skills_key = f"{self.AGENT_SKILLS_KEY_PREFIX}{agent_id}"
            skills = await self.redis_manager.redis_client.get_set_members(skills_key) or []
            
            # Try to get agent config or create a default one
            config = None
            try:
                # First try to get config from Redis
                config_key = f"{self.AGENT_CONFIG_KEY_PREFIX}{agent_id}"
                config_data = await self.redis_manager.redis_client.get_value(config_key) or {}
                
                # Ensure agent_id is in the config
                if isinstance(config_data, dict) and config_data:
                    if 'agent_id' not in config_data:
                        config_data['agent_id'] = agent_id
                    config = AgentConfig(**config_data)
                else:
                    # Try to get config from the basic agent data
                    config_from_basic = basic_agent_data.get("config", {})
                    if config_from_basic and isinstance(config_from_basic, dict):
                        if 'agent_id' not in config_from_basic:
                            config_from_basic['agent_id'] = agent_id
                        config = AgentConfig(**config_from_basic)
            except Exception as e:
                logger.warning(f"Error creating AgentConfig for agent {agent_id}: {e}")
            
            # If we couldn't create a config from existing data, use the default
            if not config:
                config = self._create_default_config(agent_id, skills)
            
            # Create Agent object
            agent = Agent(
                agent_id=agent_id,
                status=status,
                config=config,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                created_by=basic_agent_data.get("created_by")
            )
            
            # Save the full agent data for future use
            logger.info(f"Saving reconstructed agent with fields: {list(agent.dict().keys())}")
            await self.redis_manager.redis_client.set_value(
                agent_key, 
                json.dumps(agent.dict(), cls=DateTimeEncoder)
            )
            
            return agent
            
        except Exception as e:
            logger.error(f"Failed to get agent {agent_id}: {e}")
            return None
    
    async def _save_agent_to_redis(self, agent: Agent) -> bool:
        """Save an agent to Redis.
        
        Args:
            agent: The agent to save.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            agent_key = f"{self.AGENT_KEY_PREFIX}{agent.agent_id}"
            serialized_agent = json.dumps(agent.dict(), cls=DateTimeEncoder)
            await self.redis_manager.redis_client.set_value(agent_key, serialized_agent)
            return True
        except Exception as e:
            logger.error(f"Failed to save agent {agent.agent_id} to Redis: {e}")
            return False
    
    async def _record_status_change(self, agent_id: str, status: AgentStatus) -> None:
        """Record a status change in the agent's history.
        
        Args:
            agent_id: The agent ID.
            status: The new status.
        """
        try:
            status_key = f"{self.AGENT_STATUS_KEY_PREFIX}{agent_id}"
            await self.redis_manager.redis_client.add_to_list(status_key, {
                "status": status.value,
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            logger.warning(f"Failed to record status change for agent {agent_id}: {e}")
            
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
            
            # Update the agent
            agent.status = status
            agent.updated_at = datetime.now()
            
            # Ensure agent_id is set (should be already, but for safety)
            if not agent.agent_id:
                agent.agent_id = agent_id
            
            # Save the updated agent to Redis
            if not await self._save_agent_to_redis(agent):
                return False
                
            # Update the status in the agent store
            store_result = await self.agent_store.update_agent_status(agent_id, status.value)
            
            # Record the status change in history
            await self._record_status_change(agent_id, status)
            
            logger.info(f"Updated status of agent {agent_id} to {status.value}")
            return store_result
            
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
            
            # Update the agent
            agent.config = config
            agent.updated_at = datetime.now()
            
            # Save the updated agent to Redis
            if not await self._save_agent_to_redis(agent):
                return False
            
            # Create simplified agent data for the agent store
            redis_agent_data = {
                "agent_id": agent_id,
                "name": config.persona.name,
                "description": config.persona.description,
                "status": agent.status.value,
                "skills": config.skills,
                "config": config.dict()
            }
            
            # Update in the agent store
            await self.agent_store.store_agent(redis_agent_data)
            
            logger.info(f"Updated configuration of agent {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update configuration of agent {agent_id}: {e}")
            return False
    
    async def _try_get_agent_from_redis(self, agent_id: str, status_filter: Optional[AgentStatus] = None) -> Optional[Agent]:
        """Try to get an agent directly from Redis.
        
        Args:
            agent_id: The ID of the agent to get.
            status_filter: Optional status to filter by.
            
        Returns:
            Optional[Agent]: The agent if found and matching the filter, otherwise None.
        """
        try:
            agent_key = f"{self.AGENT_KEY_PREFIX}{agent_id}"
            agent_data = await self.redis_manager.redis_client.get_value(agent_key)
            
            if not agent_data or not isinstance(agent_data, dict) or 'agent_id' not in agent_data or 'config' not in agent_data:
                return None
                
            # Handle datetime fields
            agent_data = self._normalize_datetime_fields(agent_data, agent_id)
            
            # Create Agent object
            agent = Agent(**agent_data)
            
            # Apply status filter if provided
            if status_filter and agent.status != status_filter:
                return None
                
            return agent
            
        except Exception as e:
            logger.warning(f"Error getting agent {agent_id} from Redis: {e}")
            return None
    
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
            logger.info(f"Found {len(agent_ids)} agent IDs in Redis")
            
            agents = []
            
            # Process each agent ID
            for agent_id in agent_ids:
                # First try to get from Redis directly
                agent = await self._try_get_agent_from_redis(agent_id, status_filter)
                
                # If not found in Redis or doesn't match filter, try using the full get_agent method
                if not agent:
                    try:
                        agent = await self.get_agent(agent_id)
                        if agent and (not status_filter or agent.status == status_filter):
                            agents.append(agent)
                    except Exception as e:
                        logger.error(f"Error getting agent {agent_id}: {e}")
                        continue
                else:
                    agents.append(agent)
            
            # Log the results
            logger.info(f"Retrieved {len(agents)} agents successfully")
            
            # Sort by updated_at (newest first) and apply pagination
            agents.sort(key=lambda a: a.updated_at, reverse=True)
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
            await self.redis_manager.redis_client.set_value(agent_key, json.dumps(agent.dict(), cls=DateTimeEncoder))
            
            # Update the status in the agent store
            success = await self.agent_store.update_agent_status(agent_id, AgentStatus.DELETED.value)
            
            # For the MVP, we don't actually delete the agent data, just mark it as deleted
            # In a production implementation, we might have a separate cleanup process
            
            logger.info(f"Deleted agent {agent_id}")
            return success
            
        except Exception as e:
            logger.error(f"Failed to delete agent {agent_id}: {e}")
            return False