"""Redis store for delegation mappings between domains and agent IDs."""

import logging
from typing import Any, Dict, List, Optional

from shared.utils.redis_client import RedisClient

logger = logging.getLogger(__name__)


class RedisDelegationStore:
    """Store delegation mappings in Redis."""

    DOMAIN_KEY_PREFIX = "delegate:domain:"
    DOMAINS_KEY = "delegate:domains"

    def __init__(self, redis_client: Optional[RedisClient] = None) -> None:
        self.redis = redis_client or RedisClient()

    async def register_domain(
        self,
        domain: str,
        agent_id: str,
        keywords: List[str],
        skills: Optional[List[str]] = None,
    ) -> str:
        """Register a new delegation domain."""
        key = f"{self.DOMAIN_KEY_PREFIX}{domain}"
        data = {"agent_id": agent_id, "keywords": keywords, "skills": skills or []}
        await self.redis.set_value(key, data)
        await self.redis.add_to_set(self.DOMAINS_KEY, domain)
        logger.info(f"Registered delegation for domain {domain} -> {agent_id}")
        return domain

    async def get_domain(self, domain: str) -> Optional[Dict[str, Any]]:
        """Get delegation config for a domain."""
        key = f"{self.DOMAIN_KEY_PREFIX}{domain}"
        return await self.redis.get_value(key)

    async def get_all_domains(self) -> Dict[str, Dict[str, Any]]:
        """Get all domain delegations."""
        domains = await self.redis.get_set_members(self.DOMAINS_KEY)
        result: Dict[str, Dict[str, Any]] = {}
        for domain in domains:
            data = await self.get_domain(domain)
            if data:
                result[domain] = data
        return result
