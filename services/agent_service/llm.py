"""
LLM integration for the Agent Service.
"""

import logging
import os
import json
from typing import Any, Dict, List, Optional

import google.generativeai as genai
from services.agent_service.models.config import ReasoningModel

logger = logging.getLogger(__name__)

# API key for Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY or GEMINI_API_KEY == "MY_GEMINI_API_KEY":
    logger.warning("GEMINI_API_KEY not set or using placeholder value. Please set a valid API key.")

# Configure Gemini API
genai.configure(api_key=GEMINI_API_KEY)


async def call_llm(
    messages: List[Dict[str, str]],
    model: ReasoningModel = ReasoningModel.GEMINI_2_5_FLASH,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    system_prompt: Optional[str] = None,
    output_schema: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Call the LLM to get a response.
    
    Args:
        messages: List of message objects with role and content.
        model: The model to use.
        temperature: The temperature to use for generation.
        max_tokens: The maximum number of tokens to generate.
        system_prompt: Optional system prompt to include at the beginning.
        output_schema: Optional JSON schema for structured output.
        
    Returns:
        Dict[str, Any]: The LLM response.
    """
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
        # Use the proper Gemini safety setting format
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
            # Return a fallback response for JSON requests
            if output_schema:
                return {"error": "Response blocked", "fallback": True}
            return {"error": error_msg}
        
        candidate = response.candidates[0]
        
        # Check finish reason
        if hasattr(candidate, 'finish_reason'):
            finish_reason = candidate.finish_reason
            logger.info(f"Prompt to Gemini: {gemini_messages}")
            if finish_reason == 2:  # SAFETY
                error_msg = "Gemini response was blocked by safety filters"
                logger.error(error_msg)
                # Return a fallback response for JSON requests
                if output_schema:
                    return {"error": "Safety filter blocked", "fallback": True}
                return {"error": error_msg}
            elif finish_reason == 3:  # RECITATION
                error_msg = "Gemini response was blocked due to recitation concerns"
                logger.error(error_msg)
                return {"error": error_msg}
            elif finish_reason == 4:  # OTHER
                error_msg = "Gemini response was blocked for other reasons"
                logger.error(error_msg)
                return {"error": error_msg}
        
        # Try to extract content safely
        try:
            content = response.text
        except Exception as e:
            # If response.text fails, try to get content from parts
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
                # Handle empty or whitespace-only content
                if not content or not content.strip():
                    logger.error("Empty content received from Gemini")
                    return {"error": "Empty response", "fallback": True}
                
                return json.loads(content.strip())
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response as JSON: {e}")
                logger.error(f"Raw content: '{content}'")
                
                # Try to extract JSON from the response (in case the LLM wrapped the JSON in markdown code blocks)
                if "```json" in content:
                    json_content = content.split("```json")[1].split("```")[0].strip()
                    try:
                        return json.loads(json_content)
                    except json.JSONDecodeError:
                        logger.error("Failed to extract JSON from code block")
                
                # Try to find JSON-like content in the response
                import re
                json_match = re.search(r'\{[^{}]*\}', content)
                if json_match:
                    try:
                        return json.loads(json_match.group())
                    except json.JSONDecodeError:
                        logger.error("Failed to parse extracted JSON pattern")
                
                # Return a fallback response that matches expected schema structure
                return {"error": "JSON parse failed", "raw_content": content, "fallback": True}
        else:
            # Return the raw content for non-JSON responses
            return {"content": content}
            
    except Exception as e:
        logger.error(f"Error calling Gemini LLM: {e}")
        return {"error": str(e)}