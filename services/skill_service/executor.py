"""
Skill execution framework for the Agentic Platform.
"""

import logging
import importlib
import inspect
import json
import os
from typing import Any, Dict, Optional, Type, Callable, List

from shared.models.skill import Skill, SkillExecution, SkillResult
from services.skill_service.registry import SkillRegistry
from services.skill_service.validator import SkillValidator

logger = logging.getLogger(__name__)


class SkillExecutionError(Exception):
    """Exception raised for skill execution errors."""
    
    def __init__(self, message: str, skill_id: str):
        self.message = message
        self.skill_id = skill_id
        super().__init__(self.message)


class SkillExecutor:
    """Framework for executing skills in the Agentic Platform."""
    
    def __init__(self, registry: SkillRegistry, validator: SkillValidator):
        """Initialize the skill executor.
        
        Args:
            registry: The skill registry.
            validator: The skill parameter validator.
        """
        self.registry = registry
        self.validator = validator
        self.skill_implementations = {}
    
    async def register_skill_implementation(
        self, 
        skill_id: str, 
        implementation: Callable
    ) -> bool:
        """Register an implementation for a skill.
        
        Args:
            skill_id: The ID of the skill.
            implementation: The implementation function.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            # Check if skill exists
            skill = await self.registry.get_skill(skill_id)
            if not skill:
                logger.error(f"Cannot register implementation for non-existent skill {skill_id}")
                return False
            
            # Store implementation
            self.skill_implementations[skill_id] = implementation
            logger.info(f"Registered implementation for skill {skill_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register implementation for skill {skill_id}: {e}")
            return False
    
    async def execute_skill(
        self, 
        execution: SkillExecution
    ) -> SkillResult:
        """Execute a skill.
        
        Args:
            execution: The skill execution request.
            
        Returns:
            SkillResult: The result of the skill execution.
        """
        try:
            skill_id = execution.skill_id
            
            # Get skill
            skill = await self.registry.get_skill(skill_id)
            if not skill:
                raise SkillExecutionError(f"Skill {skill_id} not found", skill_id)
            
            # Validate parameters
            validation_result = self.validator.validate_parameters(skill, execution.parameters)
            if not validation_result.valid:
                error_details = json.dumps(validation_result.errors)
                raise SkillExecutionError(
                    f"Invalid parameters for skill {skill_id}: {error_details}",
                    skill_id
                )
            
            # Get implementation
            implementation = self._get_skill_implementation(skill)
            if not implementation:
                raise SkillExecutionError(
                    f"No implementation found for skill {skill_id}",
                    skill_id
                )
            
            # Execute skill
            try:
                result = await implementation(
                    parameters=validation_result.validated_params,
                    skill=skill,
                    agent_id=execution.agent_id,
                    conversation_id=execution.conversation_id
                )
                
                # Store result
                result_id = await self.registry.store_skill_result(
                    skill_id=skill_id,
                    result=result,
                    status="success",
                    agent_id=execution.agent_id,
                    conversation_id=execution.conversation_id,
                    input_params=execution.parameters
                )
                
                return SkillResult(
                    result_id=result_id,
                    skill_id=skill_id,
                    status="success",
                    result=result,
                    metadata={
                        "agent_id": execution.agent_id,
                        "conversation_id": execution.conversation_id
                    }
                )
                
            except Exception as e:
                logger.error(f"Error executing skill {skill_id}: {e}")
                error_message = str(e)
                
                # Store error
                result_id = await self.registry.store_skill_result(
                    skill_id=skill_id,
                    result={},
                    status="error",
                    error=error_message,
                    agent_id=execution.agent_id,
                    conversation_id=execution.conversation_id,
                    input_params=execution.parameters
                )
                
                return SkillResult(
                    result_id=result_id,
                    skill_id=skill_id,
                    status="error",
                    result={},
                    error=error_message,
                    metadata={
                        "agent_id": execution.agent_id,
                        "conversation_id": execution.conversation_id
                    }
                )
            
        except SkillExecutionError as e:
            logger.error(f"Skill execution error: {e.message}")
            
            # Store error
            result_id = await self.registry.store_skill_result(
                skill_id=e.skill_id,
                result={},
                status="error",
                error=e.message,
                agent_id=execution.agent_id,
                conversation_id=execution.conversation_id,
                input_params=execution.parameters
            )
            
            return SkillResult(
                result_id=result_id,
                skill_id=e.skill_id,
                status="error",
                result={},
                error=e.message,
                metadata={
                    "agent_id": execution.agent_id,
                    "conversation_id": execution.conversation_id
                }
            )
            
        except Exception as e:
            logger.error(f"Unexpected error executing skill: {e}")
            
            # Store error
            result_id = await self.registry.store_skill_result(
                skill_id=execution.skill_id,
                result={},
                status="error",
                error=str(e),
                agent_id=execution.agent_id,
                conversation_id=execution.conversation_id,
                input_params=execution.parameters
            )
            
            return SkillResult(
                result_id=result_id,
                skill_id=execution.skill_id,
                status="error",
                result={},
                error=str(e),
                metadata={
                    "agent_id": execution.agent_id,
                    "conversation_id": execution.conversation_id
                }
            )
    
    def _get_skill_implementation(self, skill: Skill) -> Optional[Callable]:
        """Get the implementation for a skill.
        
        Args:
            skill: The skill.
            
        Returns:
            Optional[Callable]: The implementation function, or None if not found.
        """
        # Check if implementation is registered directly
        if skill.skill_id in self.skill_implementations:
            return self.skill_implementations[skill.skill_id]
        
        # Try to load from skills directory
        try:
            module_name = f"services.skill_service.skills.{skill.name.lower().replace(' ', '_')}"
            module = importlib.import_module(module_name)
            
            # Look for execute function
            if hasattr(module, "execute"):
                implementation = module.execute
                
                # Register for future use
                self.skill_implementations[skill.skill_id] = implementation
                
                return implementation
            
        except (ImportError, AttributeError) as e:
            logger.error(f"Failed to load implementation for skill {skill.name}: {e}")
        
        return None
    
    async def discover_skills(self, skills_dir: Optional[str] = None) -> List[Skill]:
        """Discover skills from the skills directory.
        
        Args:
            skills_dir: Optional path to the skills directory.
                Defaults to 'services/skill_service/skills'.
                
        Returns:
            List[Skill]: List of discovered skills.
        """
        skills = []
        
        if not skills_dir:
            skills_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "skills"
            )
        
        if not os.path.isdir(skills_dir):
            logger.warning(f"Skills directory {skills_dir} does not exist")
            return skills
        
        try:
            # Find all Python files in skills directory
            for filename in os.listdir(skills_dir):
                if filename.startswith("_") or not filename.endswith(".py"):
                    continue
                
                module_name = filename[:-3]  # Remove .py extension
                
                try:
                    # Import module
                    module = importlib.import_module(f"services.skill_service.skills.{module_name}")
                    
                    # Check if module defines a skill
                    if hasattr(module, "SKILL_DEFINITION"):
                        skill_def = module.SKILL_DEFINITION
                        
                        if isinstance(skill_def, dict):
                            # Create skill from definition
                            skill = Skill(**skill_def)
                            skills.append(skill)
                            
                            # Register implementation
                            if hasattr(module, "execute"):
                                self.skill_implementations[skill.skill_id] = module.execute
                        
                        elif isinstance(skill_def, Skill):
                            skills.append(skill_def)
                            
                            # Register implementation
                            if hasattr(module, "execute"):
                                self.skill_implementations[skill_def.skill_id] = module.execute
                    
                except (ImportError, AttributeError) as e:
                    logger.error(f"Error loading skill module {module_name}: {e}")
            
            logger.info(f"Discovered {len(skills)} skills")
            return skills
            
        except Exception as e:
            logger.error(f"Error discovering skills: {e}")
            return []