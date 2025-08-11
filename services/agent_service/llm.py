"""
LLM integration for the Agent Service with Model Router.
"""

import logging
import os
import json
from typing import Any, Dict, List, Optional

import google.generativeai as genai
from services.agent_service.models.config import ReasoningModel
from shared.utils.model_router import TaskMetadata, AgentRole, TaskType
from shared.utils.llm_client import call_llm_with_routing, LLMResponse

logger = logging.getLogger(__name__)

# Legacy API key handling for backward compatibility
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY or GEMINI_API_KEY == "MY_GEMINI_API_KEY":
    logger.warning("GEMINI_API_KEY not set or using placeholder value. Please set a valid API key.")

# Configure Gemini API for legacy fallback
if GEMINI_API_KEY and GEMINI_API_KEY != "MY_GEMINI_API_KEY":
    genai.configure(api_key=GEMINI_API_KEY)


async def call_llm(
    messages: List[Dict[str, str]],
    model: ReasoningModel = ReasoningModel.GEMINI_2_5_FLASH,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    system_prompt: Optional[str] = None,
    output_schema: Optional[Dict[str, Any]] = None,
    metadata: Optional[TaskMetadata] = None,
) -> Dict[str, Any]:
    """Call the LLM to get a response with dynamic model routing.
    
    Args:
        messages: List of message objects with role and content.
        model: The model to use (ignored if metadata provided for routing).
        temperature: The temperature to use for generation.
        max_tokens: The maximum number of tokens to generate.
        system_prompt: Optional system prompt to include at the beginning.
        output_schema: Optional JSON schema for structured output.
        metadata: Optional task metadata for model routing.
        
    Returns:
        Dict[str, Any]: The LLM response.
    """
    try:
        # Use model router if metadata is provided
        if metadata:
            logger.info(f"Using model router for {metadata.agent_role}:{metadata.task_type}")
            
            response = await call_llm_with_routing(
                messages=messages,
                metadata=metadata,
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=system_prompt,
                output_schema=output_schema
            )
            
            if response.error:
                logger.error(f"Model router failed: {response.error}")
                # Fallback to legacy Gemini call
                return await _legacy_gemini_call(
                    messages, model, temperature, max_tokens, system_prompt, output_schema
                )
            
            # Convert LLMResponse to expected format
            if output_schema:
                try:
                    return json.loads(response.content) if isinstance(response.content, str) else response.content
                except json.JSONDecodeError:
                    return {"error": "Failed to parse routed response as JSON", "raw_content": response.content}
            else:
                return response.content
        
        else:
            # Fallback to legacy behavior
            logger.info(f"Using legacy Gemini call with model {model.value}")
            return await _legacy_gemini_call(
                messages, model, temperature, max_tokens, system_prompt, output_schema
            )
            
    except Exception as e:
        logger.error(f"Error in LLM call: {e}")
        return {"error": str(e)}


async def _legacy_gemini_call(
    messages: List[Dict[str, str]],
    model: ReasoningModel,
    temperature: float,
    max_tokens: int,
    system_prompt: Optional[str],
    output_schema: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Legacy Gemini API call for backward compatibility."""
    try:
        logger.info(f"Calling Gemini LLM with model {model.value}")
        
        # Check if API key is valid
        if not GEMINI_API_KEY or GEMINI_API_KEY in ["MY_GEMINI_API_KEY"]:
            logger.warning(f"Invalid or placeholder API key detected: {GEMINI_API_KEY}")
            # Return a fallback response for development
            if output_schema:
                return {"error": "Invalid API key", "fallback": True}
            else:
                return {"content": "I'm currently unable to process your request due to API configuration issues. Please check the GEMINI_API_KEY environment variable."}
        
        # Initialize the Gemini model
        gemini_model = genai.GenerativeModel(model.value)
        
        # Convert messages to Gemini format
        gemini_messages = []
        
        # Handle system prompt
        if system_prompt:
            gemini_messages.append({"role": "user", "parts": [system_prompt]})
            gemini_messages.append({"role": "model", "parts": ["I understand. I'll follow these instructions."]})
        
        # Add schema instruction if provided
        if output_schema:
            schema_instruction = f"Your response must be valid JSON conforming to this schema: {json.dumps(output_schema)}"
            if system_prompt:
                gemini_messages[0]["parts"][0] += f"\n\n{schema_instruction}"
            else:
                gemini_messages.append({"role": "user", "parts": [schema_instruction]})
                gemini_messages.append({"role": "model", "parts": ["I'll respond with valid JSON following the schema."]})
        
        # Convert OpenAI-style messages to Gemini format
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            
            if role == "system":
                # System messages are handled above
                continue
            elif role == "user":
                gemini_messages.append({"role": "user", "parts": [content]})
            elif role == "assistant":
                gemini_messages.append({"role": "model", "parts": [content]})
        
        # Configure generation parameters with safety settings
        generation_config = genai.types.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        
        # Configure safety settings to be less restrictive
        safety_settings = [
            {
                "category": genai.types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                "threshold": genai.types.HarmBlockThreshold.BLOCK_NONE
            },
            {
                "category": genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                "threshold": genai.types.HarmBlockThreshold.BLOCK_NONE
            },
            {
                "category": genai.types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                "threshold": genai.types.HarmBlockThreshold.BLOCK_NONE
            },
            {
                "category": genai.types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                "threshold": genai.types.HarmBlockThreshold.BLOCK_NONE
            }
        ]
        
        # Generate response
        if len(gemini_messages) == 0:
            # If no messages, create a simple prompt
            response = await gemini_model.generate_content_async(
                "Hello",
                generation_config=generation_config,
                safety_settings=safety_settings
            )
        elif len(gemini_messages) == 1:
            # Single message
            response = await gemini_model.generate_content_async(
                gemini_messages[0]["parts"][0],
                generation_config=generation_config,
                safety_settings=safety_settings
            )
        else:
            # Multi-turn conversation
            chat = gemini_model.start_chat(history=gemini_messages[:-1])
            response = await chat.send_message_async(
                gemini_messages[-1]["parts"][0],
                generation_config=generation_config,
                safety_settings=safety_settings
            )
        
        # Check if response was blocked by safety filters
        if not response.candidates or len(response.candidates) == 0:
            error_msg = "Gemini response was blocked - no candidates returned"
            logger.error(error_msg)
            if output_schema:
                return {"error": "Response blocked", "fallback": True}
            return {"error": error_msg}
        
        candidate = response.candidates[0]
        
        # Check finish reason
        if hasattr(candidate, 'finish_reason'):
            finish_reason = candidate.finish_reason
            if finish_reason in [2, 3, 4]:  # SAFETY, RECITATION, OTHER
                error_msg = f"Gemini response was blocked, finish_reason: {finish_reason}"
                logger.error(error_msg)
                if output_schema:
                    return {"error": "Response blocked", "fallback": True}
                return {"error": error_msg}
        
        # Try to extract content safely
        try:
            content = response.text
        except Exception as e:
            try:
                if candidate.content and candidate.content.parts:
                    content = "".join([part.text for part in candidate.content.parts if hasattr(part, 'text')])
                else:
                    error_msg = f"No valid content in Gemini response: {e}"
                    logger.error(error_msg)
                    return {"error": error_msg}
            except Exception as e2:
                error_msg = f"Failed to extract content from Gemini response: {e2}"
                logger.error(error_msg)
                return {"error": error_msg}
        
        if not content:
            error_msg = "Gemini returned empty content"
            logger.error(error_msg)
            return {"error": error_msg}
        
        # Parse JSON if schema was provided
        if output_schema:
            try:
                if not content or not content.strip():
                    logger.error("Empty content received from Gemini")
                    return {"error": "Empty response", "fallback": True}
                
                return json.loads(content.strip())
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response as JSON: {e}")
                logger.error(f"Raw content: '{content}'")
                
                # Try to extract JSON from code blocks
                if "```json" in content:
                    json_content = content.split("```json")[1].split("```")[0].strip()
                    try:
                        return json.loads(json_content)
                    except json.JSONDecodeError:
                        logger.error("Failed to extract JSON from code block")
                
                # Try to find JSON-like content
                import re
                json_match = re.search(r'\{[^{}]*\}', content)
                if json_match:
                    try:
                        return json.loads(json_match.group())
                    except json.JSONDecodeError:
                        logger.error("Failed to parse extracted JSON pattern")
                
                return {"error": "JSON parse failed", "raw_content": content, "fallback": True}
        else:
            return content
            
    except Exception as e:
        logger.error(f"Error calling legacy Gemini LLM: {e}")
        return {"error": str(e)}