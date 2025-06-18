"""
LLM integration for the Agent Service.
"""

import logging
import os
import json
import httpx
from typing import Any, Dict, List, Optional

from services.agent_service.models.config import ReasoningModel

logger = logging.getLogger(__name__)

# API key for Groq
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "MY_GROQ_API_KEY")

# Groq API endpoint
GROQ_API_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"


async def call_llm(
    messages: List[Dict[str, str]],
    model: ReasoningModel = ReasoningModel.LLAMA3_70B,
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
        # Add system prompt if provided
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages
            
        # Prepare the request payload
        payload = {
            "model": model.value,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        # Add response format if schema is provided
        if output_schema:
            payload["response_format"] = {"type": "json_object"}
            
            # Add the schema to the system prompt or create one if none exists
            schema_instruction = f"Your response must conform to the following JSON schema: {json.dumps(output_schema)}"
            
            if system_prompt:
                # Update the first message (system prompt) to include schema instructions
                payload["messages"][0]["content"] += f"\n\n{schema_instruction}"
            else:
                # Add a system message with the schema instructions
                payload["messages"] = [{"role": "system", "content": schema_instruction}] + payload["messages"]
        
        # Set up headers with API key
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        logger.info(f"Calling Groq LLM with model {model.value}")
        
        # Call Groq API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                GROQ_API_ENDPOINT,
                headers=headers,
                json=payload,
                timeout=60.0
            )
            
            # Parse response
            if response.status_code == 200:
                response_data = response.json()
                content = response_data["choices"][0]["message"]["content"]
                
                # Parse JSON if schema was provided
                if output_schema:
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse LLM response as JSON: {e}")
                        # Try to extract JSON from the response (in case the LLM wrapped the JSON in markdown code blocks)
                        if "```json" in content:
                            json_content = content.split("```json")[1].split("```")[0].strip()
                            try:
                                return json.loads(json_content)
                            except json.JSONDecodeError:
                                logger.error("Failed to extract JSON from code block")
                        
                        # Return the raw content as a fallback
                        return {"raw_content": content}
                else:
                    # Return the raw content for non-JSON responses
                    return {"content": content}
            else:
                error_message = f"Groq API request failed with status code {response.status_code}: {response.text}"
                logger.error(error_message)
                try:
                    data = response.json()
                except Exception:
                    data = {}

                failed = None
                if response.status_code == 400 and isinstance(data, dict):
                    failed = data.get("error", {}).get("failed_generation")

                if failed:
                    logger.info("Attempting to parse failed_generation content")
                    # Try simple cleanup of common issues
                    cleaned = failed.strip()
                    # Remove unmatched closing braces/quotes at the end
                    cleaned = cleaned.rstrip("}\n ")
                    if not cleaned.endswith("}"):
                        cleaned += "}"
                    try:
                        return json.loads(cleaned)
                    except Exception:
                        logger.error("Failed to parse failed_generation content")

                return {"error": error_message}
        
    except Exception as e:
        logger.error(f"Error calling LLM: {e}")
        return {"error": str(e)}