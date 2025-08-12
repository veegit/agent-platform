"""
Redis client module for handling agent data in Redis.
Provides functions for storing and retrieving agent configurations and states.
"""

import json
import logging
from typing import Any, Dict, List, Optional
import uuid

from shared.utils.redis_client import RedisClient

logger = logging.getLogger(__name__)

class RedisAgentStore:
    """Redis client for handling agent data in Redis."""
    
    # Redis key prefixes
    AGENT_KEY_PREFIX = "agent:"
    AGENT_CONFIG_KEY_PREFIX = "agent:config:"
    AGENT_STATUS_KEY_PREFIX = "agent:status:"
    AGENT_SKILLS_KEY_PREFIX = "agent:skills:"
    ALL_AGENTS_KEY = "agents:all"
    
    def __init__(self, redis_client: Optional[RedisClient] = None):
        """Initialize the Redis agent store.
        
        Args:
            redis_client: Optional Redis client. If not provided, a new one will be created.
        """
        self.redis = redis_client or RedisClient()
    
    async def store_agent(self, agent_data: Dict[str, Any]) -> str:
        """Store agent data in Redis.
        
        Args:
            agent_data: Agent data dictionary with the following keys:
                - agent_id (optional): Unique identifier. If not provided, a new UUID will be generated.
                - name: Human-readable name.
                - description: Purpose description.
                - status: "active", "inactive", etc.
                - skills: List of skill IDs the agent can use.
                - config: Configuration parameters.
                
        Returns:
            str: Agent ID.
        """
        agent_id = agent_data.get("agent_id", str(uuid.uuid4()))
        agent_data["agent_id"] = agent_id
        
        # Store the main agent data as a hash
        agent_key = f"{self.AGENT_KEY_PREFIX}{agent_id}"
        
        # Extract skill list for separate storage
        skills = agent_data.get("skills", [])
        config = agent_data.get("config", {})
        
        # Create a simplified version for the main hash
        simplified_agent = {
            "agent_id": agent_id,
            "name": agent_data.get("name", ""),
            "description": agent_data.get("description", ""),
            "status": agent_data.get("status", "inactive")
        }
        
        try:
            # Store the main agent data
            await self.redis.set_value(agent_key, simplified_agent)
            
            # Store the skills as a set
            skills_key = f"{self.AGENT_SKILLS_KEY_PREFIX}{agent_id}"
            if skills:
                await self.redis.add_to_set(skills_key, *skills)
            
            # Store the config separately
            config_key = f"{self.AGENT_CONFIG_KEY_PREFIX}{agent_id}"
            await self.redis.set_value(config_key, config)
            
            # Add agent ID to the set of all agents
            await self.redis.add_to_set(self.ALL_AGENTS_KEY, agent_id)
            
            logger.info(f"Stored agent {agent_id}")
            return agent_id
            
        except Exception as e:
            logger.error(f"Failed to store agent {agent_id}: {e}")
            raise
    
    async def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get agent data from Redis.
        
        Args:
            agent_id: Agent ID.
            
        Returns:
            Optional[Dict[str, Any]]: Agent data or None if not found.
        """
        agent_key = f"{self.AGENT_KEY_PREFIX}{agent_id}"
        skills_key = f"{self.AGENT_SKILLS_KEY_PREFIX}{agent_id}"
        config_key = f"{self.AGENT_CONFIG_KEY_PREFIX}{agent_id}"
        
        try:
            # Get the main agent data
            agent_data = await self.redis.get_value(agent_key)
            if not agent_data:
                return None
            
            # Get the skills
            skills = await self.redis.get_set_members(skills_key)
            agent_data["skills"] = skills
            
            # Get the config
            config = await self.redis.get_value(config_key, {})
            agent_data["config"] = config
            
            return agent_data
            
        except Exception as e:
            logger.error(f"Failed to get agent {agent_id}: {e}")
            return None
    
    async def list_agents(self) -> List[str]:
        """List all agent IDs.
        
        Returns:
            List[str]: List of agent IDs.
        """
        try:
            return await self.redis.get_set_members(self.ALL_AGENTS_KEY)
        except Exception as e:
            logger.error(f"Failed to list agents: {e}")
            return []
    
    async def get_all_agents(self) -> List[Dict[str, Any]]:
        """Get all agents with basic information.
        
        Returns:
            List[Dict[str, Any]]: List of agent data dictionaries.
        """
        agent_ids = await self.list_agents()
        agents = []
        
        for agent_id in agent_ids:
            agent_key = f"{self.AGENT_KEY_PREFIX}{agent_id}"
            agent_data = await self.redis.get_value(agent_key)
            if agent_data:
                agents.append(agent_data)
        
        return agents
    
    async def update_agent_status(self, agent_id: str, status: str) -> bool:
        """Update agent status.
        
        Args:
            agent_id: Agent ID.
            status: New status ("active", "inactive", etc.).
            
        Returns:
            bool: True if successful, False otherwise.
        """
        agent_key = f"{self.AGENT_KEY_PREFIX}{agent_id}"
        
        try:
            # Get existing agent data first
            existing_data = await self.redis.get_value(agent_key)
            if existing_data:
                # Update only the status field while preserving other data
                existing_data["status"] = status
                await self.redis.set_value(agent_key, existing_data)
            else:
                # If no existing data, create minimal agent data with status
                await self.redis.set_value(agent_key, {
                    "agent_id": agent_id,
                    "name": "",
                    "description": "",
                    "status": status
                })
            
            # Store the status history for auditing/debugging
            status_key = f"{self.AGENT_STATUS_KEY_PREFIX}{agent_id}"
            await self.redis.add_to_list(status_key, {
                "status": status,
                "timestamp": str(uuid.uuid1())  # UUIDv1 includes timestamp
            })
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update status for agent {agent_id}: {e}")
            return False
    
    async def update_agent_skills(self, agent_id: str, skills: List[str]) -> bool:
        """Update agent skills.
        
        Args:
            agent_id: Agent ID.
            skills: List of skill IDs.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        skills_key = f"{self.AGENT_SKILLS_KEY_PREFIX}{agent_id}"
        
        try:
            # Delete existing skills
            await self.redis.delete_key(skills_key)
            
            # Add new skills
            if skills:
                await self.redis.add_to_set(skills_key, *skills)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update skills for agent {agent_id}: {e}")
            return False
    
    async def update_agent_config(self, agent_id: str, config: Dict[str, Any]) -> bool:
        """Update agent configuration.
        
        Args:
            agent_id: Agent ID.
            config: Configuration parameters.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        config_key = f"{self.AGENT_CONFIG_KEY_PREFIX}{agent_id}"
        
        try:
            # Store the config
            await self.redis.set_value(config_key, config)
            return True
            
        except Exception as e:
            logger.error(f"Failed to update config for agent {agent_id}: {e}")
            return False
    
    async def delete_agent(self, agent_id: str) -> bool:
        """Delete agent from Redis.
        
        Args:
            agent_id: Agent ID.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        agent_key = f"{self.AGENT_KEY_PREFIX}{agent_id}"
        skills_key = f"{self.AGENT_SKILLS_KEY_PREFIX}{agent_id}"
        config_key = f"{self.AGENT_CONFIG_KEY_PREFIX}{agent_id}"
        status_key = f"{self.AGENT_STATUS_KEY_PREFIX}{agent_id}"
        
        try:
            # Delete all agent-related keys
            await self.redis.delete_key(agent_key)
            await self.redis.delete_key(skills_key)
            await self.redis.delete_key(config_key)
            await self.redis.delete_key(status_key)
            
            # Remove from the set of all agents
            await self.redis.delete_key(f"{self.ALL_AGENTS_KEY}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete agent {agent_id}: {e}")
            return False