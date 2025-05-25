"""
Reasoning node for the Agent Service.
"""

import logging
import json
from typing import Any, Dict, List, Optional, Tuple

from services.agent_service.models.state import (
    AgentState, 
    Message, 
    MessageRole, 
    ReasoningOutput,
    SkillChoice
)
from services.agent_service.models.config import AgentConfig
from services.agent_service.llm import call_llm

logger = logging.getLogger(__name__)


def _format_messages_for_llm(messages: List[Message]) -> List[Dict[str, str]]:
    """Format messages for the LLM.
    
    Args:
        messages: List of messages to format.
        
    Returns:
        List[Dict[str, str]]: Formatted messages for the LLM.
    """
    return [
        {"role": msg.role.value, "content": msg.content}
        for msg in messages
        if msg.role != MessageRole.SYSTEM  # System messages are handled separately
    ]


def _build_reasoning_prompt(
    state: AgentState,
    config: AgentConfig,
    available_skills: List[Dict[str, Any]]
) -> Tuple[str, List[Dict[str, str]]]:
    """Build the reasoning prompt for the LLM.
    
    Args:
        state: The current agent state.
        config: The agent configuration.
        available_skills: List of available skills with their details.
        
    Returns:
        Tuple[str, List[Dict[str, str]]]: The system prompt and the formatted messages.
    """
    # Format available skills for the prompt
    skills_description = ""
    for skill in available_skills:
        params_desc = []
        for param in skill.get("parameters", []):
            required = "required" if param.get("required", False) else "optional"
            default = f", default: {param.get('default')}" if "default" in param else ""
            params_desc.append(f"- {param.get('name')} ({param.get('type')}): {param.get('description')} [{required}{default}]")
        
        skills_description += f"\n## {skill.get('name')} (ID: {skill.get('skill_id')})\n"
        skills_description += f"{skill.get('description')}\n"
        skills_description += "Parameters:\n" + "\n".join(params_desc) + "\n"
    
    # Build memory context
    memory_context = ""
    
    # Extract recent entities for better reference resolution
    recent_entities = []
    for fact in state.memory.key_facts[-10:]:
        if any(entity_marker in fact.lower() for entity_marker in ["is", "was", "named", "called", "person", "entity"]):
            recent_entities.append(fact)
    
    # Add conversation summary
    if state.memory.conversation_summary:
        memory_context += f"\n### Conversation Summary\n{state.memory.conversation_summary}\n"
    
    # Add key entities section first for better reference resolution
    if recent_entities:
        memory_context += "\n### Important Entities and People\n" + "\n".join([f"- {entity}" for entity in recent_entities]) + "\n"
    
    # Add all key facts
    if state.memory.key_facts:
        memory_context += "\n### All Key Facts\n" + "\n".join([f"- {fact}" for fact in state.memory.key_facts]) + "\n"
    
    # Build system prompt
    system_prompt = f"""# {config.persona.name} - Agent System Prompt

{config.persona.description}

## Goals
{' '.join([f'- {goal}' for goal in config.persona.goals])}

## Constraints
{' '.join([f'- {constraint}' for constraint in config.persona.constraints])}

## Available Skills
You have access to the following skills to help users:{skills_description}

## Memory and Context{memory_context}

## Instructions for Reasoning
1. Always check for references to entities or concepts mentioned in previous messages (e.g., pronouns like "he", "she", "it", "they", "this", "that")
2. Resolve any references using the context from previous messages and key facts before deciding on a response
3. Think through the user's message and determine the best course of action
4. You can either:
   - Use one of your skills to gather information or take action
   - Respond directly to the user if you have enough information
5. If you choose to use a skill, specify the skill_id and parameters
6. Maintain continuity in the conversation by acknowledging previously discussed entities
7. If a user refers to a person, place, or thing mentioned earlier, ALWAYS connect it to its full reference from previous context

{config.persona.system_prompt}
"""
    
    # Format conversation history for the LLM
    formatted_messages = _format_messages_for_llm(state.messages)
    
    return system_prompt, formatted_messages


# Schema for the reasoning output
REASONING_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "thoughts": {
            "type": "string",
            "description": "Your internal thought process and reasoning"
        },
        "skill_to_use": {
            "type": ["object", "null"],
            "description": "The skill you want to use, if any",
            "properties": {
                "skill_id": {
                    "type": "string",
                    "description": "ID of the skill to execute"
                },
                "parameters": {
                    "type": "object",
                    "description": "Parameters for the skill execution"
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for choosing this skill"
                }
            },
            "required": ["skill_id", "parameters", "reason"]
        },
        "response_to_user": {
            "type": ["string", "null"],
            "description": "Your direct response to the user, if not using a skill"
        },
        "should_respond_directly": {
            "type": "boolean",
            "description": "Whether you should respond directly to the user without using a skill"
        }
    },
    "required": ["thoughts", "should_respond_directly"]
}


async def reasoning_node(
    state: AgentState,
    config: AgentConfig,
    available_skills: List[Dict[str, Any]]
) -> ReasoningOutput:
    """Execute the reasoning node.
    
    Args:
        state: The current agent state.
        config: The agent configuration.
        available_skills: List of available skills with their details.
        
    Returns:
        ReasoningOutput: The output from the reasoning node.
    """
    logger.info(f"Executing reasoning node for agent {state.agent_id}, conversation {state.conversation_id}")
    
    try:
        # Build the reasoning prompt
        system_prompt, formatted_messages = _build_reasoning_prompt(state, config, available_skills)
        
        # Call the LLM to get the reasoning output
        llm_response = await call_llm(
            messages=formatted_messages,
            model=config.reasoning_model,
            temperature=0.7,
            max_tokens=2000,
            system_prompt=system_prompt,
            output_schema=REASONING_OUTPUT_SCHEMA
        )
        
        # Log the error if there is one
        if "error" in llm_response:
            logger.error(f"Error in reasoning: {llm_response['error']}")
            state.error = llm_response["error"]
            return ReasoningOutput(
                thoughts="Error in reasoning",
                should_respond_directly=True,
                response_to_user="I'm having trouble thinking right now. Could you try again later?",
                state=state
            )
        
        # Extract the reasoning output
        thoughts = llm_response.get("thoughts", "")
        should_respond_directly = llm_response.get("should_respond_directly", False)
        response_to_user = llm_response.get("response_to_user")
        skill_to_use_data = llm_response.get("skill_to_use")
        
        # Create the skill choice if one was selected
        skill_to_use = None
        if skill_to_use_data and not should_respond_directly:
            skill_to_use = SkillChoice(
                skill_id=skill_to_use_data.get("skill_id"),
                parameters=skill_to_use_data.get("parameters", {}),
                reason=skill_to_use_data.get("reason", "")
            )
        
        # Update the agent state
        state.thought_process.append(thoughts)
        state.current_node = "reasoning"
        
        # Create the reasoning output
        return ReasoningOutput(
            thoughts=thoughts,
            skill_to_use=skill_to_use,
            response_to_user=response_to_user,
            should_respond_directly=should_respond_directly,
            state=state
        )
        
    except Exception as e:
        logger.error(f"Error in reasoning node: {e}")
        state.error = str(e)
        return ReasoningOutput(
            thoughts=f"Error in reasoning: {str(e)}",
            should_respond_directly=True,
            response_to_user="I encountered an error while processing your request. Please try again.",
            state=state
        )