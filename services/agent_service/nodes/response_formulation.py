"""
Response formulation node for the Agent Service.
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List

from services.agent_service.models.state import (
    AgentState, 
    Message, 
    MessageRole, 
    ResponseFormulationOutput
)
from services.agent_service.models.config import AgentConfig
from services.agent_service.llm import call_llm

logger = logging.getLogger(__name__)


def _format_skill_results_for_prompt(state: AgentState) -> str:
    """Format skill results for the prompt.
    
    Args:
        state: The current agent state.
        
    Returns:
        str: Formatted skill results.
    """
    if not state.skill_results:
        return "No skill results available."
    
    # Get the most recent skill result
    result = state.skill_results[-1]
    
    # Format the result based on its content and status
    if result.status == "error":
        return f"Error executing skill {result.skill_id}: {result.error}"
    
    # Format the result based on the skill type
    result_content = result.result
    
    if result.skill_id == "web-search":
        # Format web search results
        output = "Web search results:\n\n"
        
        if isinstance(result_content, dict) and "results" in result_content:
            for i, item in enumerate(result_content["results"], 1):
                output += f"{i}. {item.get('title', 'No title')}\n"
                output += f"   Link: {item.get('link', 'No link')}\n"
                output += f"   {item.get('snippet', 'No snippet')}\n\n"
        
        return output
    
    elif result.skill_id == "summarize-text":
        # Format text summarization results
        if isinstance(result_content, dict) and "summary" in result_content:
            return f"Text summarization:\n\n{result_content['summary']}"
        return "Summarization completed but no summary is available."
    
    elif result.skill_id == "ask-follow-up":
        # Format follow-up questions
        output = "Generated follow-up questions:\n\n"
        
        if isinstance(result_content, dict) and "questions" in result_content:
            for i, question in enumerate(result_content["questions"], 1):
                output += f"{i}. {question.get('question', 'No question')}\n"
                if "reason" in question:
                    output += f"   Reason: {question.get('reason')}\n\n"
        
        return output
    
    # Generic formatting for other skill types
    return f"Skill {result.skill_id} executed with result: {result_content}"


def _build_response_formulation_prompt(
    state: AgentState,
    config: AgentConfig
) -> Dict[str, Any]:
    """Build the response formulation prompt.
    
    Args:
        state: The current agent state.
        config: The agent configuration.
        
    Returns:
        Dict[str, Any]: The prompt data.
    """
    # Get the most recent user message
    user_messages = [msg for msg in state.messages if msg.role == MessageRole.USER]
    latest_user_message = user_messages[-1] if user_messages else None
    
    # Format skill results
    skill_results = _format_skill_results_for_prompt(state)
    
    # Format agent's thought process
    thought_process = "\n".join(state.thought_process[-3:]) if state.thought_process else "No thought process available."
    
    # Create system prompt
    system_prompt = f"""You are {config.persona.name}, a helpful AI assistant.

Tone: {config.persona.tone}

Your goal is to formulate a helpful response to the user's request based on:
1. The information you've gathered through skill execution
2. Your reasoning about the user's request
3. Your knowledge and expertise

Be clear, concise, and helpful in your response. If you're providing information from search results or other sources, try to synthesize and present it in a coherent way rather than just listing facts.

{config.persona.system_prompt}
"""
    
    # Format user prompt
    user_prompt = f"""## User's Most Recent Message
{latest_user_message.content if latest_user_message else "No message available."}

## Your Thought Process
{thought_process}

## Skill Execution Results
{skill_results}

Based on the above information, provide a helpful response to the user that addresses their query. Be natural and conversational in your reply, while being accurate and informative.

Your response:"""
    
    return {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt
    }


async def response_formulation_node(
    state: AgentState,
    config: AgentConfig,
    direct_response: Optional[str] = None
) -> ResponseFormulationOutput:
    """Formulate a response to the user.
    
    Args:
        state: The current agent state.
        config: The agent configuration.
        direct_response: Optional direct response to use instead of generating one.
        
    Returns:
        ResponseFormulationOutput: The formulated response.
    """
    logger.info(f"Executing response formulation node for agent {state.agent_id}, conversation {state.conversation_id}")
    
    try:
        # Check if we already have a direct response
        if direct_response:
            response_content = direct_response
        else:
            # Build the prompt
            prompt_data = _build_response_formulation_prompt(state, config)
            
            # Call the LLM to generate a response
            llm_response = await call_llm(
                messages=[{"role": "user", "content": prompt_data["user_prompt"]}],
                model=config.reasoning_model,
                temperature=0.7,
                max_tokens=1000,
                system_prompt=prompt_data["system_prompt"]
            )
            
            # Extract the response
            if "error" in llm_response:
                logger.error(f"Error generating response: {llm_response['error']}")
                response_content = "I apologize, but I'm having trouble generating a response right now. Could you try again?"
            else:
                response_content = llm_response.get("content", "")
        
        # Create the response message
        response_message = Message(
            id=str(uuid.uuid4()),
            role=MessageRole.AGENT,
            content=response_content,
            timestamp=datetime.now()
        )
        
        # Add the message to the conversation
        state.messages.append(response_message)
        
        # Update the state
        state.current_node = "response_formulation"
        
        return ResponseFormulationOutput(
            message=response_message,
            state=state
        )
        
    except Exception as e:
        logger.error(f"Error in response formulation node: {e}")
        state.error = str(e)
        
        # Create an error response
        error_message = Message(
            id=str(uuid.uuid4()),
            role=MessageRole.AGENT,
            content="I apologize, but I encountered an error while formulating my response. Could you try again?",
            timestamp=datetime.now()
        )
        
        # Add the message to the conversation
        state.messages.append(error_message)
        
        return ResponseFormulationOutput(
            message=error_message,
            state=state
        )