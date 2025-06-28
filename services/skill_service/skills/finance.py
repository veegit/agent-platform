"""Finance skill for fetching latest stock prices."""

import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

import httpx

from shared.models.skill import (
    Skill,
    SkillParameter,
    ParameterType,
    ResponseFormat,
    InvocationPattern,
)

logger = logging.getLogger(__name__)

# API key for Alpha Vantage
ALPHAVANTAGE_API_KEY = os.environ.get("ALPHAVANTAGE_API_KEY", "MY_ALPHAVANTAGE_KEY")

# Alpha Vantage endpoint
ALPHAVANTAGE_ENDPOINT = "https://www.alphavantage.co/query"

# Skill definition
SKILL_DEFINITION = Skill(
    skill_id="finance",
    name="Finance Skill",
    description="Fetch the latest stock price using the Alpha Vantage API",
    parameters=[
        SkillParameter(
            name="symbol",
            type=ParameterType.STRING,
            description="Stock ticker symbol",
            required=True,
        )
    ],
    response_format=ResponseFormat(
        schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "price": {"type": "number"},
                "timestamp": {"type": "string", "format": "date-time"},
            },
        },
        description="Latest price information for the stock symbol",
    ),
    tags=["finance", "stocks", "alpha-vantage", "external-api"],
    invocation_patterns=[
        InvocationPattern(
            pattern="stock",
            pattern_type="keyword",
            description="Matches queries about stock prices",
            priority=1,
            sample_queries=["price of AAPL", "stock price TSLA"],
            parameter_extraction={"symbol": {"type": "content"}},
        )
    ],
)


async def execute(
    parameters: Dict[str, Any],
    skill: Optional[Skill] = None,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute the finance skill to retrieve the latest stock price."""

    symbol = parameters["symbol"].upper()

    logger.info(f"Fetching latest price for {symbol} from Alpha Vantage")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                ALPHAVANTAGE_ENDPOINT,
                params={
                    "function": "GLOBAL_QUOTE",
                    "symbol": symbol,
                    "apikey": ALPHAVANTAGE_API_KEY,
                },
                timeout=10.0,
            )

            if response.status_code != 200:
                raise Exception(f"API request failed with status {response.status_code}")

            data = response.json()
            quote = data.get("Global Quote") or {}
            price_str = quote.get("05. price")
            timestamp = quote.get("07. latest trading day") or datetime.utcnow().isoformat()

            if not price_str:
                raise Exception("Price not found in API response")

            price = float(price_str)

            return {"symbol": symbol, "price": price, "timestamp": timestamp}

    except Exception as exc:
        logger.error(f"Finance skill error: {exc}")
        raise Exception(f"Failed to fetch price for {symbol}: {exc}")
