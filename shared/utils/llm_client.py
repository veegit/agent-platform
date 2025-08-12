"""
LLM Client with support for multiple providers (Direct APIs + OpenRouter).
"""

import logging
import os
import json
import httpx
import google.generativeai as genai
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass

from shared.utils.model_router import TaskMetadata, route_model, RoutingResult

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Standardized LLM response."""
    content: str
    model_used: str
    is_fallback_used: bool
    provider: str
    raw_response: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class LLMClient:
    """Multi-provider LLM client with routing support."""
    
    def __init__(self):
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY")
        self.groq_api_key = os.environ.get("GROQ_API_KEY")
        self.openrouter_api_key = os.environ.get("OPENROUTER_API_KEY")
        
        # Configure Gemini if available
        if self.gemini_api_key and self.gemini_api_key != "MY_GEMINI_API_KEY":
            genai.configure(api_key=self.gemini_api_key)
        
        # HTTP client for API calls
        self.http_client = httpx.AsyncClient(timeout=30.0)
    
    async def call_llm(
        self,
        messages: List[Dict[str, str]],
        metadata: TaskMetadata,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        system_prompt: Optional[str] = None,
        output_schema: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        """
        Call LLM with automatic model routing.
        
        Args:
            messages: List of message objects with role and content
            metadata: Task metadata for routing
            temperature: Temperature for generation
            max_tokens: Maximum tokens to generate
            system_prompt: Optional system prompt
            output_schema: Optional JSON schema for structured output
            
        Returns:
            LLMResponse object with standardized response
        """
        try:
            # Route to appropriate model
            routing_result = await route_model(metadata)
            logger.info(f"Routed to model: {routing_result.model_id} via {routing_result.provider} (fallback: {routing_result.is_fallback})")
            
            # Try the primary model first
            response = await self._call_provider(
                routing_result, messages, temperature, max_tokens, system_prompt, output_schema
            )
            
            # If primary model failed and we haven't used fallback yet, try fallback
            if response.error and not routing_result.is_fallback:
                logger.warning(f"Primary model {routing_result.model_id} failed, trying fallback model")
                
                # Get fallback model by creating new metadata with higher priority to force fallback
                from shared.utils.model_router import get_model_router
                router = get_model_router()
                
                # Get routing policy for this agent role
                role_key = metadata.agent_role.value if hasattr(metadata.agent_role, 'value') else str(metadata.agent_role)
                policy = router.routing_policies.get(role_key)
                
                if policy and policy.fallback:
                    fallback_model_config = router.models.get(policy.fallback)
                    if fallback_model_config:
                        fallback_result = RoutingResult(
                            model_id=fallback_model_config.id,
                            provider=fallback_model_config.provider,
                            is_fallback=True
                        )
                        logger.info(f"Trying fallback model: {fallback_result.model_id} via {fallback_result.provider}")
                        
                        fallback_response = await self._call_provider(
                            fallback_result, messages, temperature, max_tokens, system_prompt, output_schema
                        )
                        
                        if not fallback_response.error:
                            return fallback_response
                        else:
                            logger.error(f"Both primary and fallback models failed. Primary: {response.error}, Fallback: {fallback_response.error}")
            
            return response
                
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return LLMResponse(
                content="",
                model_used="unknown",
                is_fallback_used=False,
                provider="unknown",
                error=str(e)
            )
    
    async def _call_provider(
        self,
        routing_result: RoutingResult,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str],
        output_schema: Optional[Dict[str, Any]]
    ) -> LLMResponse:
        """Call the appropriate provider based on routing result."""
        if routing_result.provider == "gemini":
            return await self._call_gemini_direct(
                messages, routing_result.model_id, routing_result.is_fallback, temperature, max_tokens, 
                system_prompt, output_schema
            )
        elif routing_result.provider == "groq":
            return await self._call_groq_direct(
                messages, routing_result.model_id, routing_result.is_fallback, temperature, max_tokens,
                system_prompt, output_schema
            )
        elif routing_result.provider == "openrouter":
            return await self._call_openrouter(
                messages, routing_result.model_id, routing_result.is_fallback, temperature, max_tokens,
                system_prompt, output_schema
            )
        else:
            # Unknown provider - return error
            return LLMResponse(
                content="",
                model_used=routing_result.model_id,
                is_fallback_used=routing_result.is_fallback,
                provider=routing_result.provider,
                error=f"Unknown provider: {routing_result.provider}"
            )
    
    async def _call_gemini_direct(
        self,
        messages: List[Dict[str, str]],
        model_id: str,
        is_fallback: bool,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str],
        output_schema: Optional[Dict[str, Any]]
    ) -> LLMResponse:
        """Call Gemini directly via Google API."""
        try:
            if not self.gemini_api_key or self.gemini_api_key == "MY_GEMINI_API_KEY":
                logger.warning("Invalid Gemini API key, falling back to OpenRouter")
                return await self._call_openrouter(
                    messages, model_id, is_fallback, temperature, max_tokens,
                    system_prompt, output_schema
                )
            
            # Map OpenRouter model ID to Gemini model name
            gemini_model_name = self._map_to_gemini_model(model_id)
            
            # Initialize the Gemini model
            gemini_model = genai.GenerativeModel(gemini_model_name)
            
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
                    continue  # Already handled above
                elif role == "user":
                    gemini_messages.append({"role": "user", "parts": [content]})
                elif role == "assistant":
                    gemini_messages.append({"role": "model", "parts": [content]})
            
            # Configure generation parameters
            generation_config = genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
            
            # Configure safety settings to be less restrictive
            safety_settings = [
                {"category": genai.types.HarmCategory.HARM_CATEGORY_HARASSMENT, "threshold": genai.types.HarmBlockThreshold.BLOCK_NONE},
                {"category": genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, "threshold": genai.types.HarmBlockThreshold.BLOCK_NONE},
                {"category": genai.types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, "threshold": genai.types.HarmBlockThreshold.BLOCK_NONE},
                {"category": genai.types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, "threshold": genai.types.HarmBlockThreshold.BLOCK_NONE}
            ]
            
            # Generate response
            if len(gemini_messages) <= 1:
                response = await gemini_model.generate_content_async(
                    gemini_messages[0]["parts"][0] if gemini_messages else "Hello",
                    generation_config=generation_config,
                    safety_settings=safety_settings
                )
            else:
                chat = gemini_model.start_chat(history=gemini_messages[:-1])
                response = await chat.send_message_async(
                    gemini_messages[-1]["parts"][0],
                    generation_config=generation_config,
                    safety_settings=safety_settings
                )
            
            # Extract content
            if not response.candidates or len(response.candidates) == 0:
                raise Exception("Gemini response was blocked - no candidates returned")
            
            candidate = response.candidates[0]
            
            # Check finish reason
            if hasattr(candidate, 'finish_reason') and candidate.finish_reason in [2, 3, 4]:  # SAFETY, RECITATION, OTHER
                raise Exception(f"Gemini response was blocked, finish_reason: {candidate.finish_reason}")
            
            content = response.text
            if not content:
                raise Exception("Gemini returned empty content")
            
            # Parse JSON if schema was provided
            if output_schema:
                try:
                    content = json.loads(content.strip())
                except json.JSONDecodeError:
                    # Try to extract JSON from markdown code blocks
                    if "```json" in content:
                        json_content = content.split("```json")[1].split("```")[0].strip()
                        try:
                            content = json.loads(json_content)
                        except json.JSONDecodeError:
                            raise Exception("Failed to parse JSON response from Gemini")
                    else:
                        raise Exception("Failed to parse JSON response from Gemini")
            
            return LLMResponse(
                content=content if isinstance(content, str) else json.dumps(content),
                model_used=model_id,
                is_fallback_used=is_fallback,
                provider="gemini_direct",
                raw_response={"candidates": response.candidates}
            )
            
        except Exception as e:
            logger.error(f"Gemini direct API call failed: {e}")
            # Return error to let routing system handle fallback
            return LLMResponse(
                content="",
                model_used=model_id,
                is_fallback_used=is_fallback,
                provider="gemini_direct",
                error=str(e)
            )
    
    async def _call_groq_direct(
        self,
        messages: List[Dict[str, str]],
        model_id: str,
        is_fallback: bool,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str],
        output_schema: Optional[Dict[str, Any]]
    ) -> LLMResponse:
        """Call Groq directly via Groq API."""
        try:
            if not self.groq_api_key or self.groq_api_key == "MY_GROQ_API_KEY":
                logger.warning("Invalid Groq API key, falling back to OpenRouter")
                return await self._call_openrouter(
                    messages, model_id, is_fallback, temperature, max_tokens,
                    system_prompt, output_schema
                )
            
            # Map OpenRouter model ID to Groq model name
            groq_model_name = self._map_to_groq_model(model_id)
            
            # Prepare messages in OpenAI format
            api_messages = []
            
            if system_prompt:
                api_messages.append({"role": "system", "content": system_prompt})
            
            # Add schema instruction if provided
            if output_schema:
                schema_instruction = f"Your response must be valid JSON conforming to this schema: {json.dumps(output_schema)}"
                if system_prompt:
                    api_messages[0]["content"] += f"\n\n{schema_instruction}"
                else:
                    api_messages.append({"role": "system", "content": schema_instruction})
            
            api_messages.extend(messages)
            
            # Call Groq API
            payload = {
                "model": groq_model_name,
                "messages": api_messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            
            headers = {
                "Authorization": f"Bearer {self.groq_api_key}",
                "Content-Type": "application/json"
            }
            
            response = await self.http_client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json=payload,
                headers=headers
            )
            
            if response.status_code != 200:
                raise Exception(f"Groq API error: {response.status_code} - {response.text}")
            
            data = response.json()
            
            if not data.get("choices") or len(data["choices"]) == 0:
                raise Exception("No choices returned from Groq API")
            
            content = data["choices"][0]["message"]["content"]
            
            # Parse JSON if schema was provided
            if output_schema:
                try:
                    content = json.loads(content.strip())
                except json.JSONDecodeError:
                    raise Exception("Failed to parse JSON response from Groq")
            
            return LLMResponse(
                content=content if isinstance(content, str) else json.dumps(content),
                model_used=model_id,
                is_fallback_used=is_fallback,
                provider="groq_direct",
                raw_response=data
            )
            
        except Exception as e:
            logger.error(f"Groq direct API call failed: {e}")
            # Return error to let routing system handle fallback
            return LLMResponse(
                content="",
                model_used=model_id,
                is_fallback_used=is_fallback,
                provider="groq_direct",
                error=str(e)
            )
    
    async def _call_openrouter(
        self,
        messages: List[Dict[str, str]],
        model_id: str,
        is_fallback: bool,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str],
        output_schema: Optional[Dict[str, Any]]
    ) -> LLMResponse:
        """Call model via OpenRouter API."""
        try:
            if not self.openrouter_api_key or self.openrouter_api_key == "MY_OPENROUTER_API_KEY":
                raise Exception("OpenRouter API key not configured")
            
            # Prepare messages in OpenAI format
            api_messages = []
            
            if system_prompt:
                api_messages.append({"role": "system", "content": system_prompt})
            
            # Add schema instruction if provided
            if output_schema:
                schema_instruction = f"Your response must be valid JSON conforming to this schema: {json.dumps(output_schema)}"
                if system_prompt:
                    api_messages[0]["content"] += f"\n\n{schema_instruction}"
                else:
                    api_messages.append({"role": "system", "content": schema_instruction})
            
            api_messages.extend(messages)
            
            # Call OpenRouter API
            payload = {
                "model": model_id,
                "messages": api_messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            
            headers = {
                "Authorization": f"Bearer {self.openrouter_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/your-repo/agent-platform",
                "X-Title": "Agent Platform"
            }
            
            response = await self.http_client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json=payload,
                headers=headers
            )
            
            if response.status_code != 200:
                raise Exception(f"OpenRouter API error: {response.status_code} - {response.text}")
            
            data = response.json()
            
            if not data.get("choices") or len(data["choices"]) == 0:
                raise Exception("No choices returned from OpenRouter API")
            
            content = data["choices"][0]["message"]["content"]
            
            # Parse JSON if schema was provided
            if output_schema:
                try:
                    content = json.loads(content.strip())
                except json.JSONDecodeError:
                    raise Exception("Failed to parse JSON response from OpenRouter")
            
            return LLMResponse(
                content=content if isinstance(content, str) else json.dumps(content),
                model_used=model_id,
                is_fallback_used=is_fallback,
                provider="openrouter",
                raw_response=data
            )
            
        except Exception as e:
            logger.error(f"OpenRouter API call failed: {e}")
            raise e
    
    def _map_to_gemini_model(self, model_id: str) -> str:
        """Map OpenRouter model ID to Gemini model name."""
        if "2.5-flash" in model_id:
            return "gemini-2.0-flash-exp"
        elif "1.5-pro" in model_id:
            return "gemini-1.5-pro"
        elif "1.5-flash" in model_id:
            return "gemini-1.5-flash"
        else:
            return "gemini-2.0-flash-exp"  # Default
    
    def _map_to_groq_model(self, model_id: str) -> str:
        """Map OpenRouter model ID to Groq model name."""
        if "llama-4-scout-17b-16e-instruct" in model_id:
            return "llama-4-scout-17b-16e-instruct"
        elif "llama-3-8b" in model_id:
            return "llama3-8b-8192"
        else:
            return "llama3-70b-8192"  # Default
    
    async def close(self):
        """Close HTTP client."""
        await self.http_client.aclose()


# Global client instance
_llm_client_instance: Optional[LLMClient] = None

def get_llm_client() -> LLMClient:
    """Get global LLM client instance."""
    global _llm_client_instance
    if _llm_client_instance is None:
        _llm_client_instance = LLMClient()
    return _llm_client_instance

async def call_llm_with_routing(
    messages: List[Dict[str, str]],
    metadata: TaskMetadata,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    system_prompt: Optional[str] = None,
    output_schema: Optional[Dict[str, Any]] = None,
) -> LLMResponse:
    """
    Convenience function to call LLM with routing.
    
    Args:
        messages: List of message objects
        metadata: Task metadata for routing
        temperature: Generation temperature
        max_tokens: Maximum tokens
        system_prompt: Optional system prompt
        output_schema: Optional JSON schema
        
    Returns:
        LLMResponse object
    """
    client = get_llm_client()
    return await client.call_llm(
        messages, metadata, temperature, max_tokens, system_prompt, output_schema
    )