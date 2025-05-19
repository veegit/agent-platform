"""
Client for interacting with the Skill Service.
"""

import logging
import os
import httpx
from typing import Any, Dict, List, Optional

from shared.models.skill import SkillExecution, SkillResult

logger = logging.getLogger(__name__)

class SkillServiceClient:
    """Client for interacting with the Skill Service."""
    
    def __init__(self, base_url: Optional[str] = None):
        """Initialize the skill service client.
        
        Args:
            base_url: The base URL of the skill service. Defaults to environment variable.
        """
        self.base_url = base_url or os.environ.get("SKILL_SERVICE_URL", "http://localhost:8002")
        logger.info(f"Initialized Skill Service client with base URL: {self.base_url}")
    
    async def get_available_skills(self) -> List[Dict[str, Any]]:
        """Get all available skills from the skill service.
        
        Returns:
            List[Dict[str, Any]]: List of available skills.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/skills", timeout=10.0)
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get("skills", [])
                else:
                    logger.error(f"Failed to get available skills: {response.status_code} - {response.text}")
                    return []
                
        except Exception as e:
            logger.error(f"Error getting available skills: {e}")
            return []
    
    async def get_skill(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Get details of a specific skill.
        
        Args:
            skill_id: The ID of the skill to get.
            
        Returns:
            Optional[Dict[str, Any]]: The skill details, or None if not found.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/skills/{skill_id}", timeout=10.0)
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    logger.warning(f"Skill {skill_id} not found")
                    return None
                else:
                    logger.error(f"Failed to get skill {skill_id}: {response.status_code} - {response.text}")
                    return None
                
        except Exception as e:
            logger.error(f"Error getting skill {skill_id}: {e}")
            return None
    
    async def execute_skill(
        self, 
        skill_id: str, 
        parameters: Dict[str, Any],
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> Optional[SkillResult]:
        """Execute a skill.
        
        Args:
            skill_id: The ID of the skill to execute.
            parameters: The parameters for the skill execution.
            agent_id: Optional ID of the agent executing the skill.
            conversation_id: Optional ID of the conversation context.
            
        Returns:
            Optional[SkillResult]: The result of the skill execution, or None if it failed.
        """
        try:
            # Create skill execution request
            execution = SkillExecution(
                skill_id=skill_id,
                parameters=parameters,
                agent_id=agent_id,
                conversation_id=conversation_id
            )
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/skills/execute",
                    json=execution.dict(),
                    timeout=30.0  # Longer timeout for skill execution
                )
                
                if response.status_code == 200:
                    result_data = response.json()
                    
                    # Create skill result from response
                    return SkillResult(
                        result_id=result_data.get("result_id"),
                        skill_id=skill_id,
                        status=result_data.get("status"),
                        result=result_data.get("result", {}),
                        error=result_data.get("error"),
                        metadata={
                            "agent_id": agent_id,
                            "conversation_id": conversation_id
                        }
                    )
                else:
                    logger.error(f"Failed to execute skill {skill_id}: {response.status_code} - {response.text}")
                    return None
                
        except Exception as e:
            logger.error(f"Error executing skill {skill_id}: {e}")
            return None
    
    async def get_skill_result(self, result_id: str) -> Optional[SkillResult]:
        """Get a skill execution result.
        
        Args:
            result_id: The ID of the result to get.
            
        Returns:
            Optional[SkillResult]: The result, or None if not found.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/skills/results/{result_id}", timeout=10.0)
                
                if response.status_code == 200:
                    return SkillResult(**response.json())
                elif response.status_code == 404:
                    logger.warning(f"Result {result_id} not found")
                    return None
                else:
                    logger.error(f"Failed to get result {result_id}: {response.status_code} - {response.text}")
                    return None
                
        except Exception as e:
            logger.error(f"Error getting result {result_id}: {e}")
            return None