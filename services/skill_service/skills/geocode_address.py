"""
Skill implementation for geocoding an address using Google Geocode API.
"""

import os
import httpx

from shared.models.skill import (
    Skill,
    SkillParameter,
    ParameterType,
    ResponseFormat,
    InvocationPattern,
)

SKILL_DEFINITION = Skill(
    skill_id="geocode-address",
    name="Geocode Address",
    description="Convert a postal address to latitude and longitude using Google Geocode API.",
    parameters=[
        SkillParameter(
            name="address",
            type=ParameterType.STRING,
            description="The address to geocode.",
            required=True,
        ),
    ],
    response_format=ResponseFormat(
        schema={
            "type": "object",
            "properties": {
                "lat": {"type": "number"},
                "lng": {"type": "number"}
            },
            "required": ["lat", "lng"]
        },
        description="Latitude and longitude of the address.",
    ),
    tags=["geocode", "external-api"],
    invocation_patterns=[
        InvocationPattern(
            pattern="address",
            pattern_type="keyword",
            description="Detects when user provides an address to be geocoded.",
            priority=2,
            sample_queries=["Convert 1600 Amphitheatre Parkway to coordinates"],
            parameter_extraction=None,
        )
    ],
)

async def execute(
    parameters: dict,
    **kwargs,
) -> dict:
    """
    Call Google Geocode API to retrieve latitude and longitude for the given address.
    """
    api_key = os.environ.get("GOOGLE_GEOCODE_API_KEY")
    address = parameters.get("address")
    if not api_key or not address:
        raise RuntimeError("Missing Google Geocode API key or address parameter")
    url = (
        "https://maps.googleapis.com/maps/api/geocode/json"
        f"?address={httpx.utils.quote(address)}&key={api_key}"
    )
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    results = data.get("results") or []
    if not results:
        raise RuntimeError(f"Geocode API response error: {data.get('status')}")
    location = results[0].get("geometry", {}).get("location", {})
    lat = location.get("lat")
    lng = location.get("lng")
    if lat is None or lng is None:
        raise RuntimeError("No location found in Geocode response")
    return {"lat": lat, "lng": lng}