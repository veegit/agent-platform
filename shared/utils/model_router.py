"""
Model Router for dynamic LLM selection with RPM limits and fallback logic.
"""

import logging
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Literal, Tuple
from dataclasses import dataclass
from collections import defaultdict
import yaml
import os
from enum import Enum

from shared.utils.redis_client import RedisClientManager

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """Types of tasks for routing decisions."""
    REASONING = "reasoning"
    SKILL_EXECUTION = "skill_execution"
    RESPONSE_FORMULATION = "response_formulation"
    DELEGATION = "delegation"


class AgentRole(str, Enum):
    """Agent roles for routing decisions."""
    SUPERVISOR = "supervisor"
    RESEARCH = "research_agent"
    FINANCE = "finance_agent"
    CREATIVE = "creative_agent"
    GENERIC = "generic"


class CostMode(str, Enum):
    """Cost optimization modes."""
    LOW_COST = "low_cost"
    BALANCED = "balanced"
    PERFORMANCE = "performance"


@dataclass
class TaskMetadata:
    """Metadata for routing decisions."""
    agent_role: AgentRole
    task_type: TaskType
    priority: int = 1  # 1-5, higher is more urgent
    cost_mode: CostMode = CostMode.BALANCED
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None


@dataclass
class ModelConfig:
    """Configuration for a model."""
    id: str
    provider: str
    rpm_limit: int
    cost_per_1k_tokens_usd: float
    latency_ms_avg: int


@dataclass
class RoutingPolicy:
    """Routing policy for an agent role."""
    primary: str
    fallback: str


@dataclass 
class RoutingResult:
    """Result of model routing."""
    model_id: str
    provider: str
    is_fallback: bool


class RPMTracker:
    """Tracks requests per minute for models."""
    
    def __init__(self, use_redis: bool = True):
        self.use_redis = use_redis
        self.redis_manager = RedisClientManager() if use_redis else None
        self._memory_counters: Dict[str, list] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def increment_and_check(self, model_id: str, rpm_limit: int) -> bool:
        """
        Increment request counter and check if under limit.
        
        Args:
            model_id: ID of the model
            rpm_limit: RPM limit for the model
            
        Returns:
            True if under limit, False if over limit
        """
        logger.info(f"RPM tracking: increment_and_check called for {model_id} (limit: {rpm_limit}, use_redis: {self.use_redis})")
        if self.use_redis and self.redis_manager:
            return await self._redis_increment_and_check(model_id, rpm_limit)
        else:
            return await self._memory_increment_and_check(model_id, rpm_limit)
    
    async def _redis_increment_and_check(self, model_id: str, rpm_limit: int) -> bool:
        """Redis-based RPM tracking with sliding window."""
        try:
            redis_client = self.redis_manager.get_client()
            current_time = int(time.time())
            window_start = current_time - 60  # 60 seconds window
            
            # Use Redis sorted set for sliding window
            key = f"rpm_counter:{model_id}"
            logger.info(f"Redis RPM: Processing {model_id}, key={key}, current_time={current_time}")
            
            # Remove old entries outside the window
            removed_count = await redis_client.zremrangebyscore(key, 0, window_start)
            logger.info(f"Redis RPM: Removed {removed_count} old entries for {model_id}")
            
            # Count current entries
            current_count = await redis_client.zcard(key)
            logger.info(f"Redis RPM: Current count for {model_id}: {current_count}")
            
            if current_count >= rpm_limit:
                logger.warning(f"Model {model_id} RPM limit {rpm_limit} exceeded: {current_count} requests")
                return False
            
            # Add current request with timestamp as score and unique identifier as member
            unique_id = f"{current_time}:{asyncio.current_task().get_name() if asyncio.current_task() else 'unknown'}"
            added_count = await redis_client.zadd(key, {unique_id: current_time})
            logger.info(f"Redis RPM: Added {added_count} entry for {model_id}, unique_id={unique_id}")
            
            # Set expiration for cleanup
            expire_result = await redis_client.expire(key, 120)  # 2 minutes to be safe
            logger.info(f"Redis RPM: Set expiration for {model_id}: {expire_result}")
            
            logger.info(f"Model {model_id}: {current_count + 1}/{rpm_limit} RPM - SUCCESS")
            return True
            
        except Exception as e:
            logger.error(f"Redis RPM tracking failed for {model_id}: {e}")
            # Fallback to memory-based tracking
            return await self._memory_increment_and_check(model_id, rpm_limit)
    
    async def _memory_increment_and_check(self, model_id: str, rpm_limit: int) -> bool:
        """Memory-based RPM tracking (for single process deployments)."""
        async with self._lock:
            current_time = time.time()
            window_start = current_time - 60  # 60 seconds window
            
            # Clean old entries
            self._memory_counters[model_id] = [
                timestamp for timestamp in self._memory_counters[model_id]
                if timestamp > window_start
            ]
            
            if len(self._memory_counters[model_id]) >= rpm_limit:
                logger.warning(f"Model {model_id} RPM limit {rpm_limit} exceeded: {len(self._memory_counters[model_id])} requests")
                return False
            
            # Add current request
            self._memory_counters[model_id].append(current_time)
            logger.debug(f"Model {model_id}: {len(self._memory_counters[model_id])}/{rpm_limit} RPM")
            return True

    async def get_current_rpm(self, model_id: str) -> int:
        """Get current RPM for a model."""
        if self.use_redis and self.redis_manager:
            try:
                redis_client = self.redis_manager.get_client()
                current_time = int(time.time())
                window_start = current_time - 60
                key = f"rpm_counter:{model_id}"
                
                # Clean old entries and count
                await redis_client.zremrangebyscore(key, 0, window_start)
                return await redis_client.zcard(key)
            except Exception as e:
                logger.error(f"Failed to get RPM from Redis for {model_id}: {e}")
        
        # Fallback to memory
        async with self._lock:
            current_time = time.time()
            window_start = current_time - 60
            
            # Clean old entries
            self._memory_counters[model_id] = [
                timestamp for timestamp in self._memory_counters[model_id]
                if timestamp > window_start
            ]
            
            return len(self._memory_counters[model_id])


class ModelRouter:
    """Dynamic model router with RPM limits and fallback logic."""
    
    def __init__(self, config_path: str = "routing_policy.yaml"):
        self.config_path = config_path
        self.models: Dict[str, ModelConfig] = {}
        self.routing_policies: Dict[str, RoutingPolicy] = {}
        self.fallback_behavior: Dict[str, Any] = {}
        self.logging_config: Dict[str, Any] = {}
        self.rpm_tracker = RPMTracker()
        self._load_config()
    
    def _load_config(self):
        """Load routing configuration from YAML file."""
        try:
            with open(self.config_path, 'r') as file:
                config = yaml.safe_load(file)
            
            # Load model configurations
            for model_name, model_config in config.get('models', {}).items():
                self.models[model_name] = ModelConfig(**model_config)
            
            # Load routing policies
            for role, policy in config.get('routing_policy', {}).items():
                self.routing_policies[role] = RoutingPolicy(**policy)
            
            # Load fallback behavior
            self.fallback_behavior = config.get('fallback_behavior', {})
            
            # Load logging config
            self.logging_config = config.get('logging', {})
            
            logger.info(f"Loaded routing config with {len(self.models)} models and {len(self.routing_policies)} policies")
            
        except Exception as e:
            logger.error(f"Failed to load routing config from {self.config_path}: {e}")
            self._load_default_config()
    
    def _load_default_config(self):
        """Load default configuration when config file is not available."""
        logger.warning("Using default routing configuration")
        
        # Default models
        self.models = {
            "gemini_flash": ModelConfig(
                id="google/gemini-2.5-flash",
                provider="gemini",
                rpm_limit=900,
                cost_per_1k_tokens_usd=0.0002,
                latency_ms_avg=400
            ),
            "groq_llama_70b": ModelConfig(
                id="llama3-70b-8192",
                provider="groq",
                rpm_limit=30,
                cost_per_1k_tokens_usd=0.0001,
                latency_ms_avg=300
            )
        }
        
        # Default routing policies
        self.routing_policies = {
            "supervisor": RoutingPolicy(primary="gemini_flash", fallback="groq_llama_70b"),
            "research_agent": RoutingPolicy(primary="gemini_flash", fallback="groq_llama_70b"),
            "finance_agent": RoutingPolicy(primary="groq_llama_70b", fallback="gemini_flash"),
            "creative_agent": RoutingPolicy(primary="gemini_flash", fallback="groq_llama_70b"),
        }
        
        # Default fallback behavior
        self.fallback_behavior = {
            "mode": "immediate",
            "queue_retry_seconds": 60
        }
        
        # Default logging
        self.logging_config = {
            "enabled": True,
            "verbosity": "info",
            "log_fallback_events": True
        }
    
    async def get_model(self, metadata: TaskMetadata) -> RoutingResult:
        """
        Get the appropriate model for a task.
        
        Args:
            metadata: Task metadata for routing decisions
            
        Returns:
            RoutingResult with model_id, provider, and fallback status
        """
        # Get routing policy for agent role
        role_key = metadata.agent_role.value if isinstance(metadata.agent_role, AgentRole) else str(metadata.agent_role)
        policy = self.routing_policies.get(role_key)
        
        if not policy:
            logger.warning(f"No routing policy found for role {role_key}, using default")
            policy = self.routing_policies.get("supervisor", RoutingPolicy(primary="gemini_flash", fallback="groq_llama_scout"))
        
        # Try primary model first
        primary_model = self.models.get(policy.primary)
        if primary_model:
            can_use_primary = await self.rpm_tracker.increment_and_check(
                primary_model.id, primary_model.rpm_limit
            )
            
            if can_use_primary:
                if self.logging_config.get("enabled", True):
                    logger.info(f"Routing {role_key}:{metadata.task_type.value} to primary model {primary_model.id}")
                return RoutingResult(
                    model_id=primary_model.id,
                    provider=primary_model.provider,
                    is_fallback=False
                )
            else:
                if self.logging_config.get("log_fallback_events", True):
                    current_rpm = await self.rpm_tracker.get_current_rpm(primary_model.id)
                    logger.warning(f"Primary model {primary_model.id} at RPM limit ({current_rpm}/{primary_model.rpm_limit}), trying fallback")
        
        # Try fallback model
        fallback_model = self.models.get(policy.fallback)
        if fallback_model:
            can_use_fallback = await self.rpm_tracker.increment_and_check(
                fallback_model.id, fallback_model.rpm_limit
            )
            
            if can_use_fallback:
                if self.logging_config.get("log_fallback_events", True):
                    logger.warning(f"Using fallback model {fallback_model.id} for {role_key}:{metadata.task_type.value}")
                return RoutingResult(
                    model_id=fallback_model.id,
                    provider=fallback_model.provider,
                    is_fallback=True
                )
            else:
                current_rpm = await self.rpm_tracker.get_current_rpm(fallback_model.id)
                logger.error(f"Both primary and fallback models at RPM limit. Fallback: {current_rpm}/{fallback_model.rpm_limit}")
        
        # Both models at limit - handle based on fallback behavior
        if self.fallback_behavior.get("mode") == "queue":
            # For now, return the fallback model anyway and let the caller handle retry
            logger.error(f"All models at RPM limit, returning fallback model {fallback_model.id} anyway")
            return RoutingResult(
                model_id=fallback_model.id,
                provider=fallback_model.provider,
                is_fallback=True
            )
        else:
            # Immediate mode - return fallback model anyway
            logger.error(f"All models at RPM limit, returning fallback model {fallback_model.id} anyway")
            return RoutingResult(
                model_id=fallback_model.id,
                provider=fallback_model.provider,
                is_fallback=True
            )
    
    def reload_config(self):
        """Reload configuration from file."""
        logger.info("Reloading routing configuration...")
        self._load_config()
    
    async def get_routing_stats(self) -> Dict[str, Any]:
        """Get current routing statistics."""
        stats = {}
        
        for model_name, model_config in self.models.items():
            current_rpm = await self.rpm_tracker.get_current_rpm(model_config.id)
            stats[model_name] = {
                "id": model_config.id,
                "current_rpm": current_rpm,
                "rpm_limit": model_config.rpm_limit,
                "utilization_percent": (current_rpm / model_config.rpm_limit) * 100,
                "cost_per_1k_tokens": model_config.cost_per_1k_tokens_usd,
                "avg_latency_ms": model_config.latency_ms_avg
            }
        
        return stats


# Global router instance
_router_instance: Optional[ModelRouter] = None

def get_model_router() -> ModelRouter:
    """Get global model router instance."""
    global _router_instance
    if _router_instance is None:
        config_path = os.path.join(os.path.dirname(__file__), "..", "..", "routing_policy.yaml")
        _router_instance = ModelRouter(config_path)
    return _router_instance

async def route_model(metadata: TaskMetadata) -> RoutingResult:
    """
    Convenience function to route a model based on task metadata.
    
    Args:
        metadata: Task metadata
        
    Returns:
        RoutingResult with model_id, provider, and fallback status
    """
    router = get_model_router()
    return await router.get_model(metadata)