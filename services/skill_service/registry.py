"""
Skill Registry for managing skills in the Agentic Platform.
"""

import logging
from typing import Dict, List, Optional, Union

from shared.models.skill import Skill, SkillResult
from shared.utils.redis_skill_store import RedisSkillStore
from shared.utils.redis_manager import RedisManager

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Registry for managing skills in the Agentic Platform."""
    
    def __init__(self, redis_manager: Optional[RedisManager] = None):
        """Initialize the skill registry.
        
        Args:
            redis_manager: Optional Redis Manager. If not provided, a new one will be created.
        """
        self.redis_manager = redis_manager or RedisManager()
        self.skill_store = self.redis_manager.skills
        
        # In-memory cache for faster access to frequently used skills
        self._skill_cache: Dict[str, Skill] = {}
    
    async def initialize(self) -> None:
        """Initialize the skill registry."""
        # Always connect to Redis first, regardless of whether skills is None
        await self.redis_manager.connect()
    
        # Now we can safely assign the skills attribute
        self.skill_store = self.redis_manager.skills
    
        if self.skill_store is None:
            raise RuntimeError("Failed to initialize Redis skill store")
    
        # Prime the cache with all available skills
        await self.refresh_cache()
    
        logger.info("Skill registry initialized")
    
    async def refresh_cache(self) -> None:
        """Refresh the in-memory skill cache from Redis."""
        skills = await self.skill_store.get_all_skills()
        
        self._skill_cache.clear()
        for skill_data in skills:
            try:
                skill = Skill(**skill_data)
                self._skill_cache[skill.skill_id] = skill
            except Exception as e:
                logger.error(f"Failed to parse skill data: {e}")
        
        logger.info(f"Skill cache refreshed with {len(self._skill_cache)} skills")
    
    async def register_skill(self, skill: Skill) -> str:
        """Register a new skill in the registry.
        
        Args:
            skill: The skill to register.
            
        Returns:
            str: The skill ID.
        """
        try:
            # Store in Redis
            await self.skill_store.register_skill(skill.dict())
            
            # Update cache
            self._skill_cache[skill.skill_id] = skill
            
            logger.info(f"Registered skill {skill.name} with ID {skill.skill_id}")
            return skill.skill_id
            
        except Exception as e:
            logger.error(f"Failed to register skill {skill.name}: {e}")
            raise
    
    async def get_skill(self, skill_id: str) -> Optional[Skill]:
        """Get a skill by ID.
        
        Args:
            skill_id: The ID of the skill to get.
            
        Returns:
            Optional[Skill]: The skill, or None if not found.
        """
        # Check cache first
        if skill_id in self._skill_cache:
            return self._skill_cache[skill_id]
        
        # Try Redis
        try:
            skill_data = await self.skill_store.get_skill(skill_id)
            if not skill_data:
                logger.warning(f"Skill {skill_id} not found")
                return None
            
            skill = Skill(**skill_data)
            
            # Update cache
            self._skill_cache[skill_id] = skill
            
            return skill
            
        except Exception as e:
            logger.error(f"Failed to get skill {skill_id}: {e}")
            return None
    
    async def get_skills(self) -> List[Skill]:
        """Get all registered skills.
        
        Returns:
            List[Skill]: List of all registered skills.
        """
        try:
            # If cache is empty, refresh it
            if not self._skill_cache:
                await self.refresh_cache()
            
            return list(self._skill_cache.values())
            
        except Exception as e:
            logger.error(f"Failed to get skills: {e}")
            return []
    
    async def update_skill(self, skill_id: str, skill: Skill) -> bool:
        """Update a skill in the registry.
        
        Args:
            skill_id: The ID of the skill to update.
            skill: The updated skill.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            # Ensure skill_id is consistent
            if skill.skill_id != skill_id:
                skill.skill_id = skill_id
            
            # Update in Redis
            success = await self.skill_store.update_skill(skill_id, skill.dict())
            
            if success:
                # Update cache
                self._skill_cache[skill_id] = skill
                logger.info(f"Updated skill {skill.name} with ID {skill_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to update skill {skill_id}: {e}")
            return False
    
    async def delete_skill(self, skill_id: str) -> bool:
        """Delete a skill from the registry.
        
        Args:
            skill_id: The ID of the skill to delete.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            # Delete from Redis
            success = await self.skill_store.delete_skill(skill_id)
            
            if success:
                # Update cache
                if skill_id in self._skill_cache:
                    del self._skill_cache[skill_id]
                logger.info(f"Deleted skill {skill_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to delete skill {skill_id}: {e}")
            return False
    
    async def store_skill_result(self, 
                                 skill_id: str, 
                                 result: Union[Dict, str], 
                                 status: str = "success",
                                 error: Optional[str] = None,
                                 agent_id: Optional[str] = None,
                                 conversation_id: Optional[str] = None,
                                 input_params: Optional[Dict] = None) -> str:
        """Store a skill execution result.
        
        Args:
            skill_id: The ID of the skill that was executed.
            result: The result of the skill execution.
            status: The status of the execution (success or error).
            error: Error message if execution failed.
            agent_id: Optional ID of the agent that executed the skill.
            conversation_id: Optional ID of the conversation context.
            input_params: Optional input parameters used for the skill execution.
            
        Returns:
            str: The result ID.
        """
        try:
            # Create result model
            skill_result = SkillResult(
                skill_id=skill_id,
                status=status,
                result=result,
                error=error,
                metadata={
                    "agent_id": agent_id,
                    "conversation_id": conversation_id,
                    "input_params": input_params or {}
                }
            )
            
            # Store in Redis
            result_id = await self.skill_store.store_skill_result(
                skill_id=skill_id,
                result=skill_result.dict(),
                agent_id=agent_id,
                conversation_id=conversation_id,
                input_params=input_params
            )
            
            logger.info(f"Stored result {result_id} for skill {skill_id}")
            return result_id
            
        except Exception as e:
            logger.error(f"Failed to store result for skill {skill_id}: {e}")
            raise
    
    async def get_skill_result(self, result_id: str) -> Optional[SkillResult]:
        """Get a skill execution result.
        
        Args:
            result_id: The ID of the result to get.
            
        Returns:
            Optional[SkillResult]: The result, or None if not found.
        """
        try:
            result_data = await self.skill_store.get_skill_result(result_id)
            if not result_data:
                logger.warning(f"Result {result_id} not found")
                return None
            
            return SkillResult(**result_data)
            
        except Exception as e:
            logger.error(f"Failed to get result {result_id}: {e}")
            return None