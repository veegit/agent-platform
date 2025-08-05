"""
Place Search skill implementation using the Campertunity MCP server.
"""

import logging
import os
from typing import Any, Dict, Optional

from shared.utils.mcp_client import SimpleMCPClient

from shared.models.skill import (
    Skill,
    SkillParameter,
    ParameterType,
    ResponseFormat,
    InvocationPattern,
)

logger = logging.getLogger(__name__)


SKILL_DEFINITION = Skill(
    skill_id="place-search",
    name="Place Search",
    description="Search for campsites using the Campertunity MCP server",
    parameters=[
        SkillParameter(
            name="limit",
            type=ParameterType.INTEGER,
            description="Number of results (default: 50, max: 1000)",
            required=False,
            default=50,
        ),
        SkillParameter(
            name="startDate",
            type=ParameterType.STRING,
            description="Start date for availability (YYYY-MM-DD)",
            required=False,
        ),
        SkillParameter(
            name="endDate",
            type=ParameterType.STRING,
            description="End date for availability (YYYY-MM-DD)",
            required=False,
        ),
        SkillParameter(
            name="adults",
            type=ParameterType.INTEGER,
            description="Number of adults (default: 1)",
            required=False,
            default=1,
        ),
        SkillParameter(
            name="children",
            type=ParameterType.INTEGER,
            description="Number of children (default: 0)",
            required=False,
            default=0,
        ),
        SkillParameter(
            name="latitude",
            type=ParameterType.FLOAT,
            description="Center point latitude",
            required=False,
        ),
        SkillParameter(
            name="longitude",
            type=ParameterType.FLOAT,
            description="Center point longitude",
            required=False,
        ),
        SkillParameter(
            name="radius",
            type=ParameterType.FLOAT,
            description="Search radius in kilometers (default: 20)",
            required=False,
            default=20,
        ),
        SkillParameter(
            name="filters",
            type=ParameterType.ARRAY,
            description="Array of tags to filter by",
            required=False,
        ),
        SkillParameter(
            name="campgroundDescription",
            type=ParameterType.STRING,
            description="Natural language description of desired campground features",
            required=False,
        ),
    ],
    response_format=ResponseFormat(
        schema={"type": "object", "properties": {"results": {"type": "array", "items": {"type": "object"}}}},
        description="List of available campsites matching the search criteria",
    ),
    tags=["mcp", "camping", "external-api"],
    invocation_patterns=[
        InvocationPattern(
            pattern="camp",
            pattern_type="keyword",
            description="Matches queries related to camping or campsites",
            priority=3,
            sample_queries=[
                "Find campsites near Yellowstone",
                "Show me camping spots near San Francisco",
            ],
            parameter_extraction=None,
        )
    ],
)


async def execute(
    parameters: Dict[str, Any],
    skill: Optional[Skill] = None,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute the place-search skill by forwarding the request to the Campertunity MCP server.
    """
    logger.info("Executing place-search via Campertunity MCP server")
    # Prepare MCP client configuration from environment
    config = {"campertunityApiKey": os.environ.get("CAMPERTUNITY_API_KEY")}
    smithery_key = os.environ.get("SMITHERY_API_KEY") or os.environ.get("CAMPERTUNITY_API_KEY")
    base_url = os.environ.get("MCP_CAMPERTUNITY_SERVER_URL")
    async with SimpleMCPClient(config=config, smithery_api_key=smithery_key, base_url=base_url) as client:
        if not await client.initialize():
            raise RuntimeError("Failed to initialize MCP client")
        return await client.call_tool("place-search", parameters)