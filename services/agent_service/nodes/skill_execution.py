"""
Skill execution node for the Agent Service.
"""

import logging
from typing import Dict, Any, Optional

from shared.models.skill import SkillExecution, SkillResult
from services.agent_service.models.state import AgentState, SkillExecutionOutput
from services.agent_service.skill_client import SkillServiceClient

logger = logging.getLogger(__name__)


async def skill_execution_node(
    state: AgentState,
    skill_client: Optional[SkillServiceClient] = None
) -> SkillExecutionOutput:
    """Execute a skill based on the agent's decision.
    
    Args:
        state: The current agent state.
        skill_client: Optional skill service client. A new one will be created if not provided.
        
    Returns:
        SkillExecutionOutput: The result of the skill execution.
    """
    logger.info(f"Executing skill execution node for agent {state.agent_id}, conversation {state.conversation_id}")
    
    # Make sure we have a skill to execute
    if not state.current_skill:
        logger.error("No skill to execute in the current state")
        state.error = "No skill to execute"
        
        # Create an error skill result
        error_result = SkillResult(
            result_id="error",
            skill_id="error",
            status="error",
            result={},
            error="No skill to execute in the current state",
            metadata={
                "agent_id": state.agent_id,
                "conversation_id": state.conversation_id
            }
        )
        
        return SkillExecutionOutput(
            skill_result=error_result,
            state=state
        )
    
    # Use provided skill client or create a new one
    client = skill_client or SkillServiceClient()
    
    try:
        # Extract skill execution details
        skill_id = state.current_skill.skill_id
        parameters = state.current_skill.parameters
        
        logger.info(f"Executing skill {skill_id} with parameters: {parameters}")
        
        # Execute the skill
        result = await client.execute_skill(
            skill_id=skill_id,
            parameters=parameters,
            agent_id=state.agent_id,
            conversation_id=state.conversation_id
        )
        
        # Handle failed execution
        if not result:
            logger.error(f"Failed to execute skill {skill_id}")
            state.error = f"Failed to execute skill {skill_id}"
            
            # Create an error skill result
            error_result = SkillResult(
                result_id="error",
                skill_id=skill_id,
                status="error",
                result={},
                error=f"Failed to execute skill {skill_id}",
                metadata={
                    "agent_id": state.agent_id,
                    "conversation_id": state.conversation_id
                }
            )
            
            # Add the result to the agent's skill results
            state.skill_results.append(error_result)
            
            return SkillExecutionOutput(
                skill_result=error_result,
                state=state
            )
        
        # Log successful execution
        logger.info(f"Successfully executed skill {skill_id}, result status: {result.status}")
        
        # Add the result to the agent's skill results
        state.skill_results.append(result)
        
        # Add observation based on the result
        if result.status == "success":
            observation = f"Executed skill {skill_id} successfully."
            if isinstance(result.result, dict) and "summary" in result.result:
                observation += f" Summary: {result.result['summary']}"
            elif isinstance(result.result, dict) and "results" in result.result:
                num_results = len(result.result["results"])
                observation += f" Found {num_results} results."
            state.observations.append(observation)
        else:
            state.observations.append(f"Skill {skill_id} execution failed: {result.error}")
        
        # Update state
        state.current_node = "skill_execution"
        
        return SkillExecutionOutput(
            skill_result=result,
            state=state
        )
    
    except Exception as e:
        logger.error(f"Error in skill execution node: {e}")
        state.error = str(e)
        
        # Create an error skill result
        error_result = SkillResult(
            result_id="error",
            skill_id=state.current_skill.skill_id,
            status="error",
            result={},
            error=str(e),
            metadata={
                "agent_id": state.agent_id,
                "conversation_id": state.conversation_id
            }
        )
        
        # Add the result to the agent's skill results
        state.skill_results.append(error_result)
        
        return SkillExecutionOutput(
            skill_result=error_result,
            state=state
        )