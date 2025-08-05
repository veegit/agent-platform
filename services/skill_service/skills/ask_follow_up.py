"""
Ask Follow-up Questions skill implementation using Gemini API.
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
    skill_id="ask-follow-up",
    name="Ask Follow-up Questions",
    description="Generate follow-up questions based on context using Gemini API",
    parameters=[
        SkillParameter(
            name="context",
            type=ParameterType.STRING,
            description="The context to generate questions from",
            required=True
        ),
        SkillParameter(
            name="num_questions",
            type=ParameterType.INTEGER,
            description="Number of questions to generate",
            required=False,
            default=3
        ),
        SkillParameter(
            name="focus_area",
            type=ParameterType.STRING,
            description="Specific area to focus questions on",
            required=False,
            default=None
        ),
        SkillParameter(
            name="question_type",
            type=ParameterType.STRING,
            description="Type of questions to generate",
            required=False,
            default="general",
            enum=["general", "clarifying", "probing", "challenging"]
        ),
        SkillParameter(
            name="model",
            type=ParameterType.STRING,
            description="Gemini model to use for generating questions",
            required=False,
            default="gemini-2.5-flash",
            enum=GEMINI_MODELS
        )
    ],
    response_format=ResponseFormat(
        schema={
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string"},
                            "reason": {"type": "string"}
                        }
                    }
                },
                "model": {"type": "string"},
                "focus_area": {"type": "string"},
                "question_type": {"type": "string"}
            }
        },
        description="List of follow-up questions with reasoning"
    ),
    tags=["questions", "gemini", "conversation", "llm"],
    invocation_patterns=[
        InvocationPattern(
            pattern="follow-up",
            pattern_type="contains",
            description="Matches explicit requests for follow-up questions",
            priority=5,
            sample_queries=["generate follow-up questions about this", "what follow-up questions can I ask"],
            parameter_extraction={
                "context": {"type": "content"}
            }
        ),
        InvocationPattern(
            pattern="follow up",
            pattern_type="contains",
            description="Matches explicit requests for follow up questions (without hyphen)",
            priority=5,
            sample_queries=["generate follow up questions", "what follow up questions should I ask"],
            parameter_extraction={
                "context": {"type": "content"}
            }
        ),
        InvocationPattern(
            pattern="more questions",
            pattern_type="contains",
            description="Matches requests for additional questions",
            priority=4,
            sample_queries=["suggest more questions about this", "what more questions can I ask"],
            parameter_extraction={
                "context": {"type": "content"}
            }
        ),
        InvocationPattern(
            pattern="deeper",
            pattern_type="contains",
            description="Matches requests to go deeper into a topic",
            priority=3,
            sample_queries=["how can I go deeper into this topic", "help me dig deeper with questions"],
            parameter_extraction={
                "context": {"type": "content"},
                "question_type": {"type": "constant", "value": "probing"}
            }
        ),
        InvocationPattern(
            pattern="clarify",
            pattern_type="contains",
            description="Matches requests for clarifying questions",
            priority=4,
            sample_queries=["help me clarify this topic", "what clarifying questions should I ask"],
            parameter_extraction={
                "context": {"type": "content"},
                "question_type": {"type": "constant", "value": "clarifying"}
            }
        ),
        InvocationPattern(
            pattern="challenge",
            pattern_type="contains",
            description="Matches requests for challenging questions",
            priority=4,
            sample_queries=["generate challenging questions", "what critical questions can I ask"],
            parameter_extraction={
                "context": {"type": "content"},
                "question_type": {"type": "constant", "value": "challenging"}
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
    """Execute the ask follow-up questions skill.
    
    Args:
        parameters: The validated parameters for the skill.
        skill: The skill definition.
        agent_id: Optional ID of the agent executing the skill.
        conversation_id: Optional ID of the conversation context.
        
    Returns:
        Dict[str, Any]: The generated follow-up questions.
    """
    context = parameters["context"]
    num_questions = parameters.get("num_questions", 3)
    focus_area = parameters.get("focus_area")
    question_type = parameters.get("question_type", "general")
    model = parameters.get("model", "gemini-2.5-flash")
    
    focus_instruction = f" Focus on {focus_area}." if focus_area else ""
    
    logger.info(f"Generating {num_questions} follow-up questions of type {question_type} using Gemini model {model}")
    
    try:
        # Prepare question type instructions
        question_type_instructions = {
            "general": "Generate balanced, thoughtful follow-up questions.",
            "clarifying": "Generate questions that seek to clarify ambiguous points or misunderstandings.",
            "probing": "Generate questions that dive deeper into specific aspects of the topic to uncover more details.",
            "challenging": "Generate questions that politely challenge assumptions or explore alternative perspectives."
        }
        
        type_instruction = question_type_instructions.get(question_type, question_type_instructions["general"])
        
        # Create the system prompt with instructions for JSON formatting
        system_prompt = """You are an expert at generating insightful follow-up questions based on provided context. 
        You analyze the context carefully and identify areas that would benefit from further exploration.
        For each question, you provide a brief explanation of why this question would be valuable to ask.
        You always respond in valid JSON format with the structure specified by the user."""
        
        # Create the user prompt
        user_prompt = f"""
        Based on the following context, generate {num_questions} insightful follow-up questions.{focus_instruction} {type_instruction}
        
        For each question, also provide a brief explanation of why this question would be valuable to ask.
        
        Format your response as JSON with the following structure:
        {{
          "questions": [
            {{
              "question": "Question text",
              "reason": "Reasoning for asking this question"
            }},
            ...
          ]
        }}
        
        Context:
        {context}
        """
        
        # Initialize the Gemini model
        gemini_model = genai.GenerativeModel(model)
        
        # Configure generation parameters
        generation_config = genai.types.GenerationConfig(
            temperature=0.7,  # Slightly higher for more creative questions
            max_output_tokens=1000,
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
        
        # Create the full prompt with JSON schema instruction
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        # Call Gemini API
        response = await gemini_model.generate_content_async(
            full_prompt,
            generation_config=generation_config,
            safety_settings=safety_settings
        )
        
        # Extract content from response
        content = response.text
        
        # Parse the JSON response
        try:
            questions_data = json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks if present
            if "```json" in content:
                json_content = content.split("```json")[1].split("```")[0].strip()
                questions_data = json.loads(json_content)
            else:
                raise Exception("Failed to parse JSON response from Gemini")
        
        # Ensure we have the expected number of questions
        if len(questions_data["questions"]) > num_questions:
            questions_data["questions"] = questions_data["questions"][:num_questions]
        
        # Add metadata to the result
        result = questions_data
        result["model"] = model
        result["focus_area"] = focus_area if focus_area else "general"
        result["question_type"] = question_type
        
        logger.info(f"Generated {len(result['questions'])} follow-up questions successfully using {model}")
        return result
        
    except Exception as e:
        logger.error(f"Error in ask follow-up questions skill: {e}")
        raise Exception(f"Failed to generate follow-up questions: {str(e)}")