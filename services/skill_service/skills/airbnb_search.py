"""
Skill implementation for searching Airbnb listings using the Airbnb MCP server.
"""

import os

from shared.utils.mcp_client import SimpleMCPClient
from shared.models.skill import (
    Skill,
    SkillParameter,
    ParameterType,
    ResponseFormat,
    InvocationPattern,
)

SKILL_DEFINITION = Skill(
    skill_id="airbnb-search",
    name="Airbnb Search",
    description="Search for Airbnb listings using the Airbnb MCP server.",
    parameters=[
        SkillParameter(
            name="location",
            type=ParameterType.STRING,
            description="Address or place name to search for Airbnb listings.",
            required=True,
        ),
        SkillParameter(name="placeId", type=ParameterType.STRING, description="Optional place ID", required=False),
        SkillParameter(name="checkin", type=ParameterType.STRING, description="Check-in date (YYYY-MM-DD)", required=False),
        SkillParameter(name="checkout", type=ParameterType.STRING, description="Check-out date (YYYY-MM-DD)", required=False),
        SkillParameter(name="adults", type=ParameterType.INTEGER, description="Number of adults", required=False),
        SkillParameter(name="children", type=ParameterType.INTEGER, description="Number of children", required=False),
        SkillParameter(name="infants", type=ParameterType.INTEGER, description="Number of infants", required=False),
        SkillParameter(name="pets", type=ParameterType.INTEGER, description="Number of pets", required=False),
        SkillParameter(name="minPrice", type=ParameterType.INTEGER, description="Minimum price filter", required=False),
        SkillParameter(name="maxPrice", type=ParameterType.INTEGER, description="Maximum price filter", required=False),
        SkillParameter(name="cursor", type=ParameterType.STRING, description="Pagination cursor", required=False),
        SkillParameter(name="ignoreRobotsText", type=ParameterType.BOOLEAN, description="Ignore robots.txt", required=False, default=True),
    ],
    response_format=ResponseFormat(
        schema={"type": "object", "properties": {"searchResults": {"type": "array"}}},
        description="Search URL and list of Airbnb listings.",
    ),
    tags=["mcp", "airbnb", "external-api"],
    invocation_patterns=[
        InvocationPattern(
            pattern="airbnb",
            pattern_type="keyword",
            description="Matches queries related to Airbnb searches",
            priority=3,
            sample_queries=["Search Airbnb in San Francisco"],
            parameter_extraction=None,
        )
    ],
)

async def execute(
    parameters: dict,
    **kwargs,
) -> dict:
    """
    Execute the airbnb-search skill by forwarding to the Airbnb MCP server.
    """
    api_key = os.environ.get("AIRBNB_MCP_API_KEY")
    base_url = os.environ.get("MCP_AIRBNB_SERVER_URL")
    if not api_key or not base_url:
        raise RuntimeError("Missing Airbnb MCP API key or server URL")
    async with SimpleMCPClient(config={}, smithery_api_key=api_key, base_url=base_url) as client:
        if not await client.initialize():
            raise RuntimeError("Failed to initialize Airbnb MCP client")
        return await client.call_tool("airbnb_search", parameters)