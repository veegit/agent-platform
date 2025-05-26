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
    ResponseFormat,
    InvocationPattern
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
    tags=["search", "web", "external-api", "serpapi"],
    invocation_patterns=[
        # News and recent information pattern
        InvocationPattern(
            pattern="recent",
            pattern_type="keyword",
            description="Matches queries about recent news or current events",
            priority=5,  # Highest priority for news queries
            sample_queries=["any recent news about AI", "latest updates on climate change"],
            parameter_extraction={
                "query": {"type": "content"},
                "search_type": {"type": "constant", "value": "news"},
                "num_results": {"type": "constant", "value": 5}
            }
        ),
        InvocationPattern(
            pattern="latest",
            pattern_type="keyword",
            description="Matches queries about latest news or updates",
            priority=5,
            sample_queries=["latest developments in quantum computing", "what are the latest AI breakthroughs"],
            parameter_extraction={
                "query": {"type": "content"},
                "search_type": {"type": "constant", "value": "news"},
                "num_results": {"type": "constant", "value": 5}
            }
        ),
        InvocationPattern(
            pattern="news",
            pattern_type="keyword",
            description="Matches queries explicitly asking for news",
            priority=5,
            sample_queries=["news about OpenAI", "technology news this week"],
            parameter_extraction={
                "query": {"type": "content"},
                "search_type": {"type": "constant", "value": "news"},
                "num_results": {"type": "constant", "value": 5}
            }
        ),
        # Factual question patterns
        InvocationPattern(
            pattern="what",
            pattern_type="startswith",
            description="Matches factual questions starting with 'what'",
            priority=2,
            sample_queries=["what is quantum computing", "what are the effects of climate change"],
            parameter_extraction={
                "query": {"type": "content"},
                "search_type": {"type": "constant", "value": "web"},
                "num_results": {"type": "constant", "value": 5}
            }
        ),
        InvocationPattern(
            pattern="who",
            pattern_type="startswith",
            description="Matches factual questions starting with 'who'",
            priority=2,
            sample_queries=["who is the CEO of OpenAI", "who won the 2024 election"],
            parameter_extraction={
                "query": {"type": "content"},
                "search_type": {"type": "constant", "value": "web"},
                "num_results": {"type": "constant", "value": 5}
            }
        ),
        InvocationPattern(
            pattern="when",
            pattern_type="startswith",
            description="Matches factual questions starting with 'when'",
            priority=2,
            sample_queries=["when was Bitcoin created", "when is the next solar eclipse"],
            parameter_extraction={
                "query": {"type": "content"},
                "search_type": {"type": "constant", "value": "web"},
                "num_results": {"type": "constant", "value": 5}
            }
        ),
        InvocationPattern(
            pattern="where",
            pattern_type="startswith",
            description="Matches factual questions starting with 'where'",
            priority=2,
            sample_queries=["where is the Great Barrier Reef", "where can I find affordable housing"],
            parameter_extraction={
                "query": {"type": "content"},
                "search_type": {"type": "constant", "value": "web"},
                "num_results": {"type": "constant", "value": 5}
            }
        ),
        # Explicit search requests
        InvocationPattern(
            pattern="search for",
            pattern_type="contains",
            description="Matches explicit search requests",
            priority=4,
            sample_queries=["search for best restaurants in San Francisco", "please search for electric car reviews"],
            parameter_extraction={
                "query": {"type": "keyword_after", "keyword": "search for"},
                "search_type": {"type": "constant", "value": "web"},
                "num_results": {"type": "constant", "value": 5}
            }
        ),
        InvocationPattern(
            pattern="find information",
            pattern_type="contains",
            description="Matches requests to find information",
            priority=4,
            sample_queries=["find information about solar panels", "please find information on machine learning"],
            parameter_extraction={
                "query": {"type": "keyword_after", "keyword": "find information"},
                "search_type": {"type": "constant", "value": "web"},
                "num_results": {"type": "constant", "value": 5}
            }
        ),
        # Current events fallback pattern (lower priority)
        InvocationPattern(
            pattern="current",
            pattern_type="keyword",
            description="Matches queries about current events",
            priority=3,
            sample_queries=["current situation in Ukraine", "what is the current state of AI regulation"],
            parameter_extraction={
                "query": {"type": "content"},
                "search_type": {"type": "constant", "value": "news"},
                "num_results": {"type": "constant", "value": 5}
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