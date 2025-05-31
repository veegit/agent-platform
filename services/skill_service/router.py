"""
API router for the Skill Service.
"""

import logging
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, HTTPException, Depends, Body
from pydantic import BaseModel

from shared.models.skill import Skill, SkillExecution, SkillResult
from services.skill_service.registry import SkillRegistry
from services.skill_service.validator import SkillValidator
from services.skill_service.executor import SkillExecutor

logger = logging.getLogger(__name__)

# Models for API requests and responses
class SkillRegistrationResponse(BaseModel):
    skill_id: str
    message: str

class SkillExecutionResponse(BaseModel):
    result_id: str
    status: str
    result: Any
    error: Optional[str] = None

class SkillListResponse(BaseModel):
    skills: List[Skill]

class ErrorResponse(BaseModel):
    detail: str


# Create API router
router = APIRouter(
    prefix="/skills",
    tags=["skills"],
    responses={
        404: {"model": ErrorResponse, "description": "Not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)


# Dependency to get skill service components
async def get_skill_registry() -> SkillRegistry:
    """Get the skill registry."""
    from services.skill_service.main import skill_registry
    return skill_registry

async def get_skill_validator() -> SkillValidator:
    """Get the skill validator."""
    from services.skill_service.main import skill_validator
    return skill_validator

async def get_skill_executor() -> SkillExecutor:
    """Get the skill executor."""
    from services.skill_service.main import skill_executor
    return skill_executor


# API endpoints
@router.post("/register", response_model=SkillRegistrationResponse)
async def register_skill(
    skill: Skill,
    registry: SkillRegistry = Depends(get_skill_registry)
):
    """Register a new skill."""
    try:
        skill_id = await registry.register_skill(skill)
        return SkillRegistrationResponse(
            skill_id=skill_id,
            message=f"Skill '{skill.name}' registered successfully"
        )
    except Exception as e:
        logger.error(f"Error registering skill: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to register skill: {str(e)}")


@router.get("", response_model=SkillListResponse)
async def list_skills(
    registry: SkillRegistry = Depends(get_skill_registry)
):
    """List all registered skills."""
    try:
        skills = await registry.get_skills()
        return SkillListResponse(skills=skills)
    except Exception as e:
        logger.error(f"Error listing skills: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list skills: {str(e)}")


@router.get("/{skill_id}", response_model=Skill)
async def get_skill(
    skill_id: str,
    registry: SkillRegistry = Depends(get_skill_registry)
):
    """Get a skill by ID."""
    try:
        skill = await registry.get_skill(skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
        return skill
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting skill {skill_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get skill: {str(e)}")


@router.post("/execute", response_model=SkillExecutionResponse)
async def execute_skill(
    execution: SkillExecution,
    executor: SkillExecutor = Depends(get_skill_executor)
):
    """Execute a skill."""
    try:
        result = await executor.execute_skill(execution)
        return SkillExecutionResponse(
            result_id=result.result_id,
            status=result.status,
            result=result.result,
            error=result.error
        )
    except Exception as e:
        logger.error(f"Error executing skill: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to execute skill: {str(e)}")


@router.get("/results/{result_id}", response_model=SkillResult)
async def get_skill_result(
    result_id: str,
    registry: SkillRegistry = Depends(get_skill_registry)
):
    """Get a skill execution result by ID."""
    try:
        result = await registry.get_skill_result(result_id)
        if not result:
            raise HTTPException(status_code=404, detail=f"Result {result_id} not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting result {result_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get result: {str(e)}")


@router.put("/{skill_id}", response_model=SkillRegistrationResponse)
async def update_skill(
    skill_id: str,
    skill: Skill,
    registry: SkillRegistry = Depends(get_skill_registry)
):
    """Update a skill."""
    try:
        # Check if skill exists
        existing_skill = await registry.get_skill(skill_id)
        if not existing_skill:
            raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
        
        # Update skill
        success = await registry.update_skill(skill_id, skill)
        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to update skill {skill_id}")
        
        return SkillRegistrationResponse(
            skill_id=skill_id,
            message=f"Skill '{skill.name}' updated successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating skill {skill_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update skill: {str(e)}")


@router.delete("/{skill_id}", response_model=Dict[str, str])
async def delete_skill(
    skill_id: str,
    registry: SkillRegistry = Depends(get_skill_registry)
):
    """Delete a skill."""
    try:
        # Check if skill exists
        existing_skill = await registry.get_skill(skill_id)
        if not existing_skill:
            raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
        
        # Delete skill
        success = await registry.delete_skill(skill_id)
        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to delete skill {skill_id}")
        
        return {"message": f"Skill {skill_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting skill {skill_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete skill: {str(e)}")

@router.get("/health")
async def health():
    return {"status": "ok"}