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
from shared.models.skill import SkillExecution
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
    skill_specific_instructions = ""
    available_skill_ids = []
    
    for skill in available_skills:
        # Store available skill IDs
        skill_id = skill.get("skill_id")
        available_skill_ids.append(skill_id)
        
        # Format skill parameters
        params_desc = []
        for param in skill.get("parameters", []):
            required = "required" if param.get("required", False) else "optional"
            default = f", default: {param.get('default')}" if "default" in param else ""
            params_desc.append(f"- {param.get('name')} ({param.get('type')}): {param.get('description')} [{required}{default}]")
        
        # Add to main skills description
        skills_description += f"\n## {skill.get('name')} (ID: {skill_id})\n"
        skills_description += f"{skill.get('description')}\n"
        skills_description += "Parameters:\n" + "\n".join(params_desc) + "\n"
        
        # Generate skill-specific instructions
        if skill_id == "web-search":
            skill_specific_instructions += """
- Use the web-search skill when:
  * Asked about current events, recent news, or trending topics
  * Asked about factual information that might have changed since your training
  * Asked for the latest information about companies, products, or public figures
  * When the query contains terms like "latest", "recent", "news", "current", "update", or "today"
  * Use search_type="news" for current events and recent developments
  * Include key entities and time-related terms in the query
"""
        elif skill_id == "calculator":
            skill_specific_instructions += """
- Use the calculator skill for any mathematical calculations or conversions
"""
        elif skill_id == "code-interpreter":
            skill_specific_instructions += """
- Use the code-interpreter skill for executing code, analyzing data, or generating plots
"""
        # Add more skill-specific instructions as needed
    
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

## When to Use Skills
You have access to the following skills: {', '.join(available_skill_ids)}
{skill_specific_instructions}

## General Guidelines
1. Only respond directly to the user if:
   - The information requested is general knowledge unlikely to have changed
   - The question is purely conceptual, philosophical, or opinion-based
   - The query is about interpreting or explaining something in the current conversation
   - You don't have access to a relevant skill for the task
2. If you choose to use a skill, specify the skill_id and parameters clearly
3. Maintain continuity in the conversation by acknowledging previously discussed entities
4. If a user refers to a person, place, or thing mentioned earlier, ALWAYS connect it to its full reference from previous context

{config.persona.system_prompt}
"""
    
    # Format conversation history for the LLM
    formatted_messages = _format_messages_for_llm(state.messages)
    
    return system_prompt, formatted_messages


# Schema for the reasoning output - simplified to reduce LLM errors
REASONING_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "thoughts": {
            "type": "string",
            "description": "Your thoughts about the user's message and how to respond"
        },
        "should_respond_directly": {
            "type": "boolean",
            "description": "Whether you should respond directly to the user without using a skill"
        },
        "skill_id": {
            "type": ["string", "null"],
            "description": "The ID of the skill to use (if should_respond_directly is false)"
        },
        "skill_parameters": {
            "type": ["object", "null"],
            "description": "Parameters for the skill execution (if should_respond_directly is false)",
        },
        "skill_reason": {
            "type": ["string", "null"],
            "description": "Reason for choosing this skill (if should_respond_directly is false)"
        },
        "response_to_user": {
            "type": ["string", "null"],
            "description": "Your direct response to the user, if not using a skill"
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
    
    # Debug logging for available skills
    skill_ids = [skill.get("skill_id") for skill in available_skills]
    logger.info(f"Available skills for agent {state.agent_id}: {skill_ids}")
    
    # Check if this is a news or recent information query
    last_message = state.messages[-1] if state.messages else None
    should_use_web_search = False
    web_search_available = any(skill.get("skill_id") == "web-search" for skill in available_skills)
    
    if last_message and last_message.role == MessageRole.USER:
        content_lower = last_message.content.lower()
        news_indicators = ["recent", "latest", "news", "update", "today", "yesterday", "this week", "this year"]
        
        if any(indicator in content_lower for indicator in news_indicators):
            should_use_web_search = True
            logger.info(f"News/recent info query detected: {last_message.content}")
    
    # FAST PATH: If this is a news query and web search is available, use it directly
    if should_use_web_search and web_search_available:
        logger.info("CRITICAL: Using direct web search bypass for news query - no LLM involvement")
        
        # Extract clean search query from the user message
        search_query = last_message.content.strip()
        # Ensure it's safe for JSON and API calls
        search_query = search_query.replace('"', '').replace('\n', ' ').replace('\\', '').strip()
        
        # Use news search type for news queries
        search_type = "news" if "news" in search_query.lower() else "web"
        logger.info(f"Using search type: {search_type} for query: '{search_query}'")
        
        # Create the skill directly without LLM
        thoughts = f"The user is asking about recent news or information: '{search_query}'. I will use the web-search skill to find the latest information."
        
        try:
            # Create skill execution objects
            skill_to_use = SkillChoice(
                skill_id="web-search",
                parameters={
                    "query": search_query,
                    "search_type": search_type,
                    "num_results": 5
                },
                reason="This query is asking for recent information or news that requires an up-to-date web search."
            )
            
            # Set the current_skill in the agent state directly
            state.current_skill = SkillExecution(
                skill_id="web-search",
                parameters={
                    "query": search_query,
                    "search_type": search_type,
                    "num_results": 5
                },
                agent_id=state.agent_id,
                conversation_id=state.conversation_id
            )
            
            # Update agent state
            state.thought_process.append(thoughts)
            state.current_node = "reasoning"
            
            logger.info(f"Fast path using skill: web-search with parameters: {{'query': '{search_query}', 'search_type': '{search_type}', 'num_results': 5}}")
            
            # Return reasoning output with explicit skill_to_use
            return ReasoningOutput(
                thoughts=thoughts,
                should_respond_directly=False,
                response_to_user=None,
                skill_to_use=skill_to_use,
                state=state
            )
            
        except Exception as e:
            logger.error(f"Error setting up direct web search: {e}")
            # Continue with normal reasoning if direct method fails
            logger.info("Falling back to standard reasoning flow after direct web search setup failed")
    
    try:
        # Build the reasoning prompt
        system_prompt, formatted_messages = _build_reasoning_prompt(state, config, available_skills)
        
        # Add explicit guidance for web search if appropriate
        if should_use_web_search and web_search_available:
            logger.info("Adding explicit web search guidance to prompt")
            system_prompt += """
\n\nNOTE: This query appears to be asking for recent news or current information. You SHOULD use the web-search skill to provide up-to-date information.\n\n
            
IMPORTANT JSON FORMATTING INSTRUCTIONS:
1. You MUST return a valid JSON object with the following format:
{
  "thoughts": "Your thinking process here",
  "should_respond_directly": false,
  "skill_id": "web-search",
  "skill_parameters": {
    "query": "The search query",
    "search_type": "news",
    "num_results": 5
  },
  "skill_reason": "Reason for using web-search",
  "response_to_user": null
}

2. Double-check that all quotes are properly closed
3. Do not use line breaks within string values
4. Keep boolean values as true or false (not strings)
5. For a news query, always set should_respond_directly to false and use the web-search skill
"""
            
            # Make sure LLM uses a lower temperature for better JSON formatting
            temperature = 0.2
        else:
            temperature = 0.7
        
        # Call the LLM to get the reasoning output
        llm_response = await call_llm(
            messages=formatted_messages,
            model=config.reasoning_model,
            temperature=temperature,  # Use the dynamic temperature setting
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
        
        # Extract the reasoning output with the simplified schema
        thoughts = llm_response.get("thoughts", "")
        should_respond_directly = llm_response.get("should_respond_directly", False)
        response_to_user = llm_response.get("response_to_user")
        
        # Get skill details from the flattened schema
        skill_id = llm_response.get("skill_id")
        skill_parameters = llm_response.get("skill_parameters", {})
        skill_reason = llm_response.get("skill_reason", "")
        
        # Build skill_to_use_data from the flattened properties
        skill_to_use_data = None
        if skill_id and not should_respond_directly:
            skill_to_use_data = {
                "skill_id": skill_id,
                "parameters": skill_parameters or {},
                "reason": skill_reason or "This skill is appropriate for the user's request."
            }
        
        # Override decision for news queries if web search is available
        if should_use_web_search and web_search_available:
            # Force the use of web search instead of direct response
            logger.info("Overriding LLM decision to use web-search for news query")
            should_respond_directly = False
            
            # Extract clean search query from the user message
            # Remove any characters that might cause JSON formatting issues
            search_query = last_message.content
            # Ensure clean query without characters that might break JSON
            search_query = search_query.replace('"', '').replace('\n', ' ').replace('\\', '').strip()
            
            # Use a safer search type selection
            search_type = "news" if "news" in search_query.lower() else "web"
            logger.info(f"Using search type: {search_type} for query: {search_query}")
            
            # CRITICAL: Force the web search skill to be used - this will bypass any LLM decision
            # Create a valid SkillChoice object directly, not relying on the LLM's output
            logger.info("FORCING use of web-search skill for news query regardless of LLM decision")
            
            try:
                # ===== CONFIGURATION-BASED SKILL MATCHING SYSTEM =====
                # Instead of hardcoded rules, we use the invocation patterns from the skill definitions
                
                # Helper function to match content against a pattern based on pattern_type
                def match_pattern(content: str, pattern: str, pattern_type: str) -> bool:
                    content = content.lower()  # Normalize content for case-insensitive matching
                    
                    if pattern_type == "keyword":
                        return pattern.lower() in content
                    elif pattern_type == "regex":
                        import re
                        try:
                            return bool(re.search(pattern, content))
                        except re.error:
                            logger.error(f"Invalid regex pattern: {pattern}")
                            return False
                    elif pattern_type == "startswith":
                        return content.startswith(pattern.lower())
                    elif pattern_type == "contains":
                        return pattern.lower() in content
                    else:
                        logger.warning(f"Unknown pattern type: {pattern_type}")
                        return False
                
                # Extract parameters based on the parameter extraction rules
                def extract_parameters(content: str, skill_def: Dict[str, Any], pattern_match: Dict[str, Any]) -> Dict[str, Any]:
                    # Start with default values for optional parameters
                    params = {}
                    
                    # Apply parameter extraction if available
                    extraction_rules = pattern_match.get("parameter_extraction")
                    if extraction_rules:
                        for param_name, extraction_rule in extraction_rules.items():
                            # This is a simplified version - in production, you'd want more sophisticated extraction
                            # For example, using regex groups or NLP
                            if extraction_rule.get("type") == "content":
                                # Use the entire content as the parameter value
                                params[param_name] = content.strip()
                            elif extraction_rule.get("type") == "keyword_after":
                                # Extract content after a keyword
                                keyword = extraction_rule.get("keyword", "")
                                if keyword and keyword in content.lower():
                                    after_keyword = content.lower().split(keyword, 1)[1].strip()
                                    params[param_name] = after_keyword
                    
                    # Fill in any missing required parameters with reasonable defaults
                    for param in skill_def.get("parameters", []):
                        param_name = param.get("name")
                        if param_name not in params:
                            if param.get("required", False):
                                if param.get("default") is not None:
                                    params[param_name] = param.get("default")
                                elif param.get("type") == "string":
                                    params[param_name] = content.strip()  # Use full content as default
                    
                    # Sanitize all string parameters to prevent JSON issues
                    for key, value in params.items():
                        if isinstance(value, str):
                            params[key] = value.replace('"', '').replace('\n', ' ').replace('\\', '').strip()
                    
                    return params
                
                # Attempt to match a skill to the user's message
                matched_skill = None
                matched_parameters = None
                matched_reason = None
                highest_priority = -1
                
                if state.messages and state.messages[-1].role == MessageRole.USER:
                    last_message_content = state.messages[-1].content
                    
                    # Try each available skill
                    for skill_def in available_skills:
                        skill_id = skill_def.get("skill_id")
                        
                        # Skip if no invocation patterns defined
                        if not skill_def.get("invocation_patterns"):
                            continue
                        
                        # Try each invocation pattern for this skill
                        for pattern in skill_def.get("invocation_patterns", []):
                            pattern_str = pattern.get("pattern", "")
                            pattern_type = pattern.get("pattern_type", "keyword")
                            priority = pattern.get("priority", 0)
                            
                            # Skip patterns with lower priority than what we've already matched
                            if priority <= highest_priority:
                                continue
                            
                            if match_pattern(last_message_content, pattern_str, pattern_type):
                                matched_skill = skill_id
                                matched_parameters = extract_parameters(
                                    last_message_content, skill_def, pattern
                                )
                                matched_reason = pattern.get("description", f"Message matched pattern: {pattern_str}")
                                highest_priority = priority
                                logger.info(f"Matched skill '{skill_id}' with pattern '{pattern_str}' (priority {priority})")
                    
                    if matched_skill:
                        logger.info(f"Final skill match: '{matched_skill}' with reason: {matched_reason}")
                    else:
                        logger.info("No skill matched the user message")
                    
                    # Create a valid SkillChoice object directly, not relying on the LLM's output
                    skill_to_use = SkillChoice(
                        skill_id=matched_skill,
                        parameters=matched_parameters,
                        reason=matched_reason
                    )
                    
                    # Also store as data for backup
                    skill_to_use_data = {
                        "skill_id": matched_skill,
                        "parameters": matched_parameters,
                        "reason": matched_reason
                    }
                    
                    # Add reasoning to thoughts
                    thoughts += "\n\nI've determined this is a query about recent events or news, so I should use the matched skill to get the most current information."
                    
                    # Set the current_skill in the agent state directly
                    state.current_skill = SkillExecution(
                        skill_id=matched_skill,
                        parameters=matched_parameters,
                        agent_id=state.agent_id,
                        conversation_id=state.conversation_id
                    )
                    
                else:
                    logger.info("No user message to match against skills")
                    
            except Exception as e:
                logger.error(f"Error creating skill parameters: {e}")
                # Fall back to direct response if parameter creation fails
                should_respond_directly = True
                skill_to_use_data = None
                skill_to_use = None
            state.current_skill = None
        
        # Update the agent state
        state.thought_process.append(thoughts)
        state.current_node = "reasoning"
        
        # Create the reasoning output - explicitly log what we're returning
        logger.info(f"Reasoning output - should_respond_directly: {should_respond_directly}, skill_to_use: {skill_to_use}")
        
        # Force skill_to_use to be set and should_respond_directly to be False for web search queries
        if should_use_web_search and web_search_available and skill_to_use:
            logger.info("Explicitly enforcing web search skill execution")
            should_respond_directly = False
            
            # Make sure we include the skill details in logging
            if skill_to_use:
                logger.info(f"Using skill: {skill_to_use.skill_id} with parameters: {skill_to_use.parameters}")
        
        return ReasoningOutput(
            thoughts=thoughts,
            should_respond_directly=should_respond_directly,
            response_to_user=response_to_user if should_respond_directly else None,
            skill_to_use=skill_to_use,
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