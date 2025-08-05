"""
Summarize Text skill implementation using Gemini API.
"""

import logging
import os
import json
from typing import Any, Dict, List, Optional

import google.generativeai as genai
from shared.models.skill import (
    Skill,
    SkillParameter,
    ParameterType,
    ResponseFormat,
    InvocationPattern
)

logger = logging.getLogger(__name__)

# API key for Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "MY_GEMINI_API_KEY")

# Configure Gemini API
genai.configure(api_key=GEMINI_API_KEY)

# Gemini model options
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-1.5-pro", "gemini-1.5-flash"]

# Skill definition
SKILL_DEFINITION = Skill(
    skill_id="summarize-text",
    name="Summarize Text",
    description="Summarize text content using Gemini API",
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
            description="Gemini model to use for summarization",
            required=False,
            default="gemini-2.5-flash",
            enum=GEMINI_MODELS
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
    tags=["summarization", "gemini", "text-processing", "llm"],
    invocation_patterns=[
        InvocationPattern(
            pattern="summarize",
            pattern_type="startswith",
            description="Matches explicit requests to summarize content",
            priority=5,
            sample_queries=["summarize this article", "summarize the following text"],
            parameter_extraction={
                "text": {"type": "keyword_after", "keyword": "summarize"}
            }
        ),
        InvocationPattern(
            pattern="summary",
            pattern_type="contains",
            description="Matches requests that mention creating a summary",
            priority=4,
            sample_queries=["give me a summary of this", "provide a summary of the following"],
            parameter_extraction={
                "text": {"type": "content"}
            }
        ),
        InvocationPattern(
            pattern="condense",
            pattern_type="contains",
            description="Matches requests to condense information",
            priority=4,
            sample_queries=["condense this information", "condense the following text"],
            parameter_extraction={
                "text": {"type": "keyword_after", "keyword": "condense"}
            }
        ),
        InvocationPattern(
            pattern="key points",
            pattern_type="contains",
            description="Matches requests for key points from text",
            priority=4,
            sample_queries=["extract key points from this", "what are the key points in this text"],
            parameter_extraction={
                "text": {"type": "content"},
                "format": {"type": "constant", "value": "key_points"}
            }
        ),
        InvocationPattern(
            pattern="bullet points",
            pattern_type="contains",
            description="Matches requests for bullet point summaries",
            priority=4,
            sample_queries=["give me bullet points from this", "summarize in bullet points"],
            parameter_extraction={
                "text": {"type": "content"},
                "format": {"type": "constant", "value": "bullet_points"}
            }
        ),
        InvocationPattern(
            pattern="tldr",
            pattern_type="contains",
            description="Matches 'too long; didn't read' requests",
            priority=5,
            sample_queries=["tldr on this article", "give me a tldr"],
            parameter_extraction={
                "text": {"type": "content"},
                "max_tokens": {"type": "constant", "value": 150}
            }
        )
    ]
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
    model = parameters.get("model", "gemini-2.5-flash")
    
    logger.info(f"Executing text summarization with Gemini model {model} in {format_type} format")
    
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
        
        # Initialize the Gemini model
        gemini_model = genai.GenerativeModel(model)
        
        # Configure generation parameters
        generation_config = genai.types.GenerationConfig(
            temperature=0.3,  # Lower temperature for more focused summaries
            max_output_tokens=max_tokens,
        )
        
        # Configure safety settings to be less restrictive
        safety_settings = [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_ONLY_HIGH"
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_ONLY_HIGH"
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_ONLY_HIGH"
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_ONLY_HIGH"
            }
        ]
        
        # Create the full prompt
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        # Call Gemini API
        response = await gemini_model.generate_content_async(
            full_prompt,
            generation_config=generation_config,
            safety_settings=safety_settings
        )
        
        # Extract summary from response
        summary = response.text
        
        # Prepare result (note: Gemini doesn't provide token usage in the same way)
        result = {
            "summary": summary,
            "tokens_used": 0,  # Gemini doesn't provide token count in response
            "format": format_type,
            "model": model
        }
        
        logger.info(f"Text summarization completed successfully using {model}")
        return result
        
    except Exception as e:
        logger.error(f"Error in summarize text skill: {e}")
        raise Exception(f"Failed to summarize text: {str(e)}")