"""
Redis client module for handling skill data and results in Redis.
Provides functions for storing and retrieving skill configurations and execution results.
"""

import json
import logging
from typing import Any, Dict, List, Optional
import uuid
from datetime import datetime

from shared.utils.redis_client import RedisClient

logger = logging.getLogger(__name__)

class RedisSkillStore:
    """Redis client for handling skill data and results in Redis."""
    
    # Redis key prefixes
    SKILL_KEY_PREFIX = "skill:"
    SKILL_RESULT_KEY_PREFIX = "skill:result:"
    SKILL_RESULT_AGENT_PREFIX = "agent:skill:results:"
    SKILL_RESULT_CONVERSATION_PREFIX = "conversation:skill:results:"
    ALL_SKILLS_KEY = "skills:all"
    
    def __init__(self, redis_client: Optional[RedisClient] = None):
        """Initialize the Redis skill store.
        
        Args:
            redis_client: Optional Redis client. If not provided, a new one will be created.
        """
        self.redis = redis_client or RedisClient()
    
    async def register_skill(self, skill_data: Dict[str, Any]) -> str:
        """Register a new skill.
        
        Args:
            skill_data: Skill data dictionary with the following keys:
                - skill_id (optional): Unique identifier. If not provided, a new UUID will be generated.
                - name: Human-readable name.
                - description: What the skill does.
                - parameters: Required and optional parameters.
                - response_format: Expected response structure.
                
        Returns:
            str: Skill ID.
        """
        skill_id = skill_data.get("skill_id", str(uuid.uuid4()))
        skill_data["skill_id"] = skill_id
        
        skill_key = f"{self.SKILL_KEY_PREFIX}{skill_id}"
        
        try:
            # Store the skill data
            await self.redis.set_hash(skill_key, skill_data)
            
            # Add skill ID to the set of all skills
            await self.redis.add_to_set(self.ALL_SKILLS_KEY, skill_id)
            
            logger.info(f"Registered skill {skill_id}")
            return skill_id
            
        except Exception as e:
            logger.error(f"Failed to register skill {skill_id}: {e}")
            raise
    
    async def get_skill(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Get skill data.
        
        Args:
            skill_id: Skill ID.
            
        Returns:
            Optional[Dict[str, Any]]: Skill data or None if not found.
        """
        skill_key = f"{self.SKILL_KEY_PREFIX}{skill_id}"
        
        try:
            skill_data = await self.redis.get_hash(skill_key)
            return skill_data or None
            
        except Exception as e:
            logger.error(f"Failed to get skill {skill_id}: {e}")
            return None
    
    async def list_skills(self) -> List[str]:
        """List all skill IDs.
        
        Returns:
            List[str]: List of skill IDs.
        """
        try:
            return await self.redis.get_set_members(self.ALL_SKILLS_KEY)
            
        except Exception as e:
            logger.error(f"Failed to list skills: {e}")
            return []
    
    async def get_all_skills(self) -> List[Dict[str, Any]]:
        """Get all skills.
        
        Returns:
            List[Dict[str, Any]]: List of skill data dictionaries.
        """
        skill_ids = await self.list_skills()
        skills = []
        
        for skill_id in skill_ids:
            skill_data = await self.get_skill(skill_id)
            if skill_data:
                skills.append(skill_data)
        
        return skills
    
    async def update_skill(self, skill_id: str, skill_data: Dict[str, Any]) -> bool:
        """Update skill data.
        
        Args:
            skill_id: Skill ID.
            skill_data: Updated skill data.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        skill_key = f"{self.SKILL_KEY_PREFIX}{skill_id}"
        
        try:
            # Ensure skill_id is preserved
            skill_data["skill_id"] = skill_id
            
            # Update the skill data
            await self.redis.set_hash(skill_key, skill_data)
            
            logger.info(f"Updated skill {skill_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update skill {skill_id}: {e}")
            return False
    
    async def delete_skill(self, skill_id: str) -> bool:
        """Delete a skill.
        
        Args:
            skill_id: Skill ID.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        skill_key = f"{self.SKILL_KEY_PREFIX}{skill_id}"
        
        try:
            # Delete the skill data
            await self.redis.delete_key(skill_key)
            
            # Remove from the set of all skills
            await self.redis.delete_key(self.ALL_SKILLS_KEY)
            
            logger.info(f"Deleted skill {skill_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete skill {skill_id}: {e}")
            return False
    
    async def store_skill_result(self, 
                                 skill_id: str, 
                                 result: Any, 
                                 agent_id: Optional[str] = None, 
                                 conversation_id: Optional[str] = None,
                                 input_params: Optional[Dict[str, Any]] = None) -> str:
        """Store a skill execution result.
        
        Args:
            skill_id: Skill ID.
            result: Execution result.
            agent_id: Optional agent ID.
            conversation_id: Optional conversation ID.
            input_params: Optional input parameters used for the skill execution.
            
        Returns:
            str: Result ID.
        """
        result_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        
        result_data = {
            "result_id": result_id,
            "skill_id": skill_id,
            "timestamp": timestamp,
            "agent_id": agent_id,
            "conversation_id": conversation_id,
            "input_params": input_params or {},
            "result": result
        }
        
        result_key = f"{self.SKILL_RESULT_KEY_PREFIX}{result_id}"
        
        try:
            # Store the result
            await self.redis.set_value(result_key, result_data)
            
            # Add to agent's results if agent_id is provided
            if agent_id:
                agent_results_key = f"{self.SKILL_RESULT_AGENT_PREFIX}{agent_id}"
                await self.redis.add_to_list(agent_results_key, result_id)
            
            # Add to conversation's results if conversation_id is provided
            if conversation_id:
                conversation_results_key = f"{self.SKILL_RESULT_CONVERSATION_PREFIX}{conversation_id}"
                await self.redis.add_to_list(conversation_results_key, result_id)
            
            logger.info(f"Stored skill result {result_id} for skill {skill_id}")
            return result_id
            
        except Exception as e:
            logger.error(f"Failed to store skill result for skill {skill_id}: {e}")
            raise
    
    async def get_skill_result(self, result_id: str) -> Optional[Dict[str, Any]]:
        """Get a skill execution result.
        
        Args:
            result_id: Result ID.
            
        Returns:
            Optional[Dict[str, Any]]: Result data or None if not found.
        """
        result_key = f"{self.SKILL_RESULT_KEY_PREFIX}{result_id}"
        
        try:
            return await self.redis.get_value(result_key)
            
        except Exception as e:
            logger.error(f"Failed to get skill result {result_id}: {e}")
            return None
    
    async def get_agent_skill_results(self, agent_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get skill execution results for an agent.
        
        Args:
            agent_id: Agent ID.
            limit: Maximum number of results to retrieve.
            
        Returns:
            List[Dict[str, Any]]: List of result data dictionaries.
        """
        agent_results_key = f"{self.SKILL_RESULT_AGENT_PREFIX}{agent_id}"
        
        try:
            # Get result IDs
            result_ids = await self.redis.get_list(agent_results_key)
            result_ids = result_ids[-limit:] if limit and len(result_ids) > limit else result_ids
            
            # Get results
            results = []
            for result_id in result_ids:
                result = await self.get_skill_result(result_id)
                if result:
                    results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to get skill results for agent {agent_id}: {e}")
            return []
    
    async def get_conversation_skill_results(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Get skill execution results for a conversation.
        
        Args:
            conversation_id: Conversation ID.
            
        Returns:
            List[Dict[str, Any]]: List of result data dictionaries.
        """
        conversation_results_key = f"{self.SKILL_RESULT_CONVERSATION_PREFIX}{conversation_id}"
        
        try:
            # Get result IDs
            result_ids = await self.redis.get_list(conversation_results_key)
            
            # Get results
            results = []
            for result_id in result_ids:
                result = await self.get_skill_result(result_id)
                if result:
                    results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to get skill results for conversation {conversation_id}: {e}")
            return []
    
    async def clear_old_results(self, older_than_days: int = 7) -> int:
        """Clear old skill execution results.
        
        Args:
            older_than_days: Clear results older than this many days.
            
        Returns:
            int: Number of results cleared.
        """
        # This would require scanning through all results and checking timestamps
        # For large datasets, this could be inefficient
        # A better approach would be to use Redis' built-in TTL feature
        # For the MVP, we'll skip the implementation of this method
        logger.warning("clear_old_results is not implemented in the MVP")
        return 0