"""
Web Search skill implementation using SerpAPI.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from serpapi import GoogleSearch

from shared.models.skill import (
    Skill,
    SkillParameter,
    ParameterType,
    ResponseFormat
)

logger = logging.getLogger(__name__)

# API key for SerpAPI
SERPAPI_API_KEY = os.environ.get("SERPAPI_API_KEY", "MY_SERP_API_KEY")

# Skill definition
SKILL_DEFINITION = Skill(
    skill_id="web-search",
    name="Web Search",
    description="Search the web for information using Google search via SerpAPI",
    parameters=[
        SkillParameter(
            name="query",
            type=ParameterType.STRING,
            description="The search query",
            required=True
        ),
        SkillParameter(
            name="num_results",
            type=ParameterType.INTEGER,
            description="Number of results to return",
            required=False,
            default=5
        ),
        SkillParameter(
            name="include_images",
            type=ParameterType.BOOLEAN,
            description="Whether to include image results",
            required=False,
            default=False
        ),
        SkillParameter(
            name="search_type",
            type=ParameterType.STRING,
            description="Type of search to perform",
            required=False,
            default="web",
            enum=["web", "news", "videos", "shopping"]
        )
    ],
    response_format=ResponseFormat(
        schema={
            "type": "object",
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "link": {"type": "string"},
                            "snippet": {"type": "string"},
                            "displayedLink": {"type": "string"}
                        }
                    }
                },
                "image_results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "thumbnail": {"type": "string"},
                            "source": {"type": "string"},
                            "title": {"type": "string"},
                            "link": {"type": "string"}
                        }
                    }
                }
            }
        },
        description="List of search results with titles, links, and snippets"
    ),
    tags=["search", "web", "external-api", "serpapi"]
)


async def execute(
    parameters: Dict[str, Any],
    skill: Optional[Skill] = None,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None
) -> Dict[str, Any]:
    """Execute the web search skill.
    
    Args:
        parameters: The validated parameters for the skill.
        skill: The skill definition.
        agent_id: Optional ID of the agent executing the skill.
        conversation_id: Optional ID of the conversation context.
        
    Returns:
        Dict[str, Any]: The search results.
    """
    query = parameters["query"]
    num_results = parameters.get("num_results", 5)
    include_images = parameters.get("include_images", False)
    search_type = parameters.get("search_type", "web")
    
    logger.info(f"Executing {search_type} search via SerpAPI for query: {query}")
    
    try:
        # Build search parameters
        search_params = {
            "q": query,
            "api_key": SERPAPI_API_KEY,
            "num": num_results,
            "hl": "en",
            "gl": "us"
        }
        
        # Handle different search types
        if search_type == "news":
            search_params["tbm"] = "nws"
        elif search_type == "videos":
            search_params["tbm"] = "vid"
        elif search_type == "shopping":
            search_params["tbm"] = "shop"
        
        # Execute search
        search = GoogleSearch(search_params)
        results = search.get_dict()
        
        # Format response
        formatted_results = {
            "results": [],
            "image_results": []
        }
        
        # Extract organic results based on search type
        if search_type == "news" and "news_results" in results:
            for result in results["news_results"][:num_results]:
                formatted_results["results"].append({
                    "title": result.get("title", ""),
                    "link": result.get("link", ""),
                    "snippet": result.get("snippet", ""),
                    "displayedLink": result.get("source", "")
                })
        elif search_type == "videos" and "video_results" in results:
            for result in results["video_results"][:num_results]:
                formatted_results["results"].append({
                    "title": result.get("title", ""),
                    "link": result.get("link", ""),
                    "snippet": result.get("snippet", ""),
                    "displayedLink": result.get("source", "")
                })
        elif search_type == "shopping" and "shopping_results" in results:
            for result in results["shopping_results"][:num_results]:
                formatted_results["results"].append({
                    "title": result.get("title", ""),
                    "link": result.get("link", ""),
                    "snippet": result.get("snippet", f"Price: {result.get('price', 'N/A')}"),
                    "displayedLink": result.get("source", "")
                })
        elif "organic_results" in results:
            for result in results["organic_results"][:num_results]:
                formatted_results["results"].append({
                    "title": result.get("title", ""),
                    "link": result.get("link", ""),
                    "snippet": result.get("snippet", ""),
                    "displayedLink": result.get("displayed_link", "")
                })
        
        # Extract image results if requested
        if include_images and "images_results" in results:
            for img in results["images_results"][:num_results]:
                formatted_results["image_results"].append({
                    "thumbnail": img.get("thumbnail", ""),
                    "source": img.get("source", ""),
                    "title": img.get("title", ""),
                    "link": img.get("link", "")
                })
        
        logger.info(f"Web search completed with {len(formatted_results['results'])} results")
        return formatted_results
        
    except Exception as e:
        logger.error(f"Error in web search skill: {e}")
        raise Exception(f"Failed to execute web search: {str(e)}")