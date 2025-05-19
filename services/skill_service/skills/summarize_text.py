"""
Summarize Text skill implementation using Groq API.
"""

import logging
import os
import httpx
import json
from typing import Any, Dict, List, Optional

from shared.models.skill import (
    Skill,
    SkillParameter,
    ParameterType,
    ResponseFormat
)

logger = logging.getLogger(__name__)

# API key for Groq
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "MY_GROQ_API_KEY")

# Groq API endpoint
GROQ_API_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

# Groq model options
GROQ_MODELS = ["llama3-8b-8192", "llama3-70b-8192", "mixtral-8x7b-32768", "gemma-7b-it"]

# Skill definition
SKILL_DEFINITION = Skill(
    skill_id="summarize-text",
    name="Summarize Text",
    description="Summarize text content using Groq API",
    parameters=[
        SkillParameter(
            name="text",
            type=ParameterType.STRING,
            description="The text to summarize",
            required=True
        ),
        SkillParameter(
            name="max_tokens",
            type=ParameterType.INTEGER,
            description="Maximum length of summary in tokens",
            required=False,
            default=300
        ),
        SkillParameter(
            name="format",
            type=ParameterType.STRING,
            description="Format of the summary",
            required=False,
            default="paragraph",
            enum=["paragraph", "bullet_points", "key_points"]
        ),
        SkillParameter(
            name="model",
            type=ParameterType.STRING,
            description="Groq model to use for summarization",
            required=False,
            default="llama3-70b-8192",
            enum=GROQ_MODELS
        )
    ],
    response_format=ResponseFormat(
        schema={
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "tokens_used": {"type": "integer"},
                "format": {"type": "string"},
                "model": {"type": "string"}
            }
        },
        description="Summary of the provided text"
    ),
    tags=["summarization", "groq", "text-processing", "llm"]
)


async def execute(
    parameters: Dict[str, Any],
    skill: Optional[Skill] = None,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None
) -> Dict[str, Any]:
    """Execute the summarize text skill.
    
    Args:
        parameters: The validated parameters for the skill.
        skill: The skill definition.
        agent_id: Optional ID of the agent executing the skill.
        conversation_id: Optional ID of the conversation context.
        
    Returns:
        Dict[str, Any]: The summary results.
    """
    text = parameters["text"]
    max_tokens = parameters.get("max_tokens", 300)
    format_type = parameters.get("format", "paragraph")
    model = parameters.get("model", "llama3-70b-8192")
    
    logger.info(f"Executing text summarization with Groq model {model} in {format_type} format")
    
    try:
        # Prepare format instructions based on format type
        format_instructions = {
            "paragraph": "Provide a concise summary in paragraph form.",
            "bullet_points": "Provide a summary in bullet point form, with each main point on a new line starting with - ",
            "key_points": "Extract and list the key points or main ideas from the text, with each point on a new line starting with * "
        }
        
        instruction = format_instructions.get(format_type, format_instructions["paragraph"])
        
        # Create the prompt
        system_prompt = f"You are an expert summarizer. Your task is to summarize text concisely and accurately, preserving the most important information."
        user_prompt = f"Summarize the following text. {instruction}\n\nText to summarize:\n{text}"
        
        # Prepare the request payload
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3  # Lower temperature for more focused summaries
        }
        
        # Set up headers with API key
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Call Groq API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                GROQ_API_ENDPOINT,
                headers=headers,
                json=payload,
                timeout=30.0
            )
            
            # Parse response
            if response.status_code == 200:
                response_data = response.json()
                summary = response_data["choices"][0]["message"]["content"]
                
                # Get token usage
                total_tokens = response_data.get("usage", {}).get("total_tokens", 0)
                
                # Prepare result
                result = {
                    "summary": summary,
                    "tokens_used": total_tokens,
                    "format": format_type,
                    "model": model
                }
                
                logger.info(f"Text summarization completed successfully using {model}")
                return result
            else:
                error_message = f"Groq API request failed with status code {response.status_code}: {response.text}"
                logger.error(error_message)
                raise Exception(error_message)
        
    except Exception as e:
        logger.error(f"Error in summarize text skill: {e}")
        raise Exception(f"Failed to summarize text: {str(e)}")