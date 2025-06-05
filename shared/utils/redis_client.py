"""
Redis client module for handling all interactions with Redis.
Provides functions for storing and retrieving various types of data.
"""

import logging
from typing import Any, Dict, List, Optional, Union
import os
import redis.asyncio as redis
from redis.exceptions import RedisError

import json
from shared.utils.json_utils import dumps, loads

logger = logging.getLogger(__name__)

class RedisClient:
    """Redis client for handling all interactions with Redis."""
    
    def __init__(self, host: str = None, port: int = None, db: int = 0, password: str = None):
        """Initialize the Redis client.
        
        Args:
            host: Redis host. Defaults to os.environ.get("REDIS_HOST", "localhost").
            port: Redis port. Defaults to int(os.environ.get("REDIS_PORT", 6379)).
            db: Redis db. Defaults to int(os.environ.get("REDIS_DB", 0)).
            password: Redis password. Defaults to os.environ.get("REDIS_PASSWORD").
        """
        self.host = host or os.environ.get("REDIS_HOST", "localhost")
        self.port = port or int(os.environ.get("REDIS_PORT", 6379))
        self.db = db if db is not None else int(os.environ.get("REDIS_DB", 0))
        self.password = password or os.environ.get("REDIS_PASSWORD")
        
        self.redis = None
        self._connect()
    
    def _connect(self) -> None:
        """Connect to Redis."""
        try:
            self.redis = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password,
                decode_responses=True
            )
            logger.info(f"Connected to Redis at {self.host}:{self.port}/{self.db}")
        except RedisError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    async def ping(self) -> bool:
        """Check if Redis is alive.
        
        Returns:
            bool: True if Redis is alive, False otherwise.
        """
        try:
            return await self.redis.ping()
        except RedisError as e:
            logger.error(f"Failed to ping Redis: {e}")
            return False
    
    async def set_value(self, key: str, value: Any, expiry: Optional[int] = None) -> bool:
        """Set a key-value pair in Redis.
        
        Args:
            key: The key.
            value: The value (will be JSON-serialized if not a string).
            expiry: Optional expiry time in seconds.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            if not isinstance(value, str):
                value = dumps(value)
            
            if expiry:
                return await self.redis.setex(key, expiry, value)
            else:
                return await self.redis.set(key, value)
        except (RedisError, TypeError) as e:
            logger.error(f"Failed to set value for key {key}: {e}")
            return False
    
    async def get_value(self, key: str, default: Any = None) -> Any:
        """Get a value from Redis.
        
        Args:
            key: The key.
            default: Default value if key doesn't exist.
            
        Returns:
            The value (JSON-deserialized if possible) or default.
        """
        try:
            value = await self.redis.get(key)
            if value is None:
                return default
            
            try:
                return loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        except RedisError as e:
            logger.error(f"Failed to get value for key {key}: {e}")
            return default
    
    async def delete_key(self, key: str) -> bool:
        """Delete a key from Redis.
        
        Args:
            key: The key to delete.
            
        Returns:
            bool: True if key was deleted, False otherwise.
        """
        try:
            return await self.redis.delete(key) > 0
        except RedisError as e:
            logger.error(f"Failed to delete key {key}: {e}")
            return False

    async def key_exists(self, key: str) -> bool:
        """Check if a key exists in Redis.
        
        Args:
            key: The key to check.
            
        Returns:
            bool: True if key exists, False otherwise.
        """
        try:
            return await self.redis.exists(key) > 0
        except RedisError as e:
            logger.error(f"Failed to check if key {key} exists: {e}")
            return False

    async def add_to_list(self, key: str, value: Any) -> bool:
        """Add a value to a list in Redis.
        
        Args:
            key: The list key.
            value: The value to add (will be JSON-serialized if not a string).
            
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            if not isinstance(value, str):
                value = dumps(value)
            
            return await self.redis.rpush(key, value) > 0
        except (RedisError, TypeError) as e:
            logger.error(f"Failed to add value to list {key}: {e}")
            return False
    
    async def get_list(self, key: str) -> List[Any]:
        """Get all values from a list in Redis.
        
        Args:
            key: The list key.
            
        Returns:
            List of values (JSON-deserialized if possible).
        """
        try:
            values = await self.redis.lrange(key, 0, -1)
            result = []
            
            for value in values:
                try:
                    result.append(loads(value))
                except (json.JSONDecodeError, TypeError):
                    result.append(value)
            
            return result
        except RedisError as e:
            logger.error(f"Failed to get list {key}: {e}")
            return []

    async def set_hash(self, key: str, field_value_map: Dict[str, Any]) -> bool:
        """Set multiple fields in a hash.
        
        Args:
            key: The hash key.
            field_value_map: Dictionary mapping fields to values.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            serialized_map = {}
            for field, value in field_value_map.items():
                if not isinstance(value, str):
                    serialized_map[field] = dumps(value)
                else:
                    serialized_map[field] = value
            
            return await self.redis.hset(key, mapping=serialized_map) >= 0
        except (RedisError, TypeError) as e:
            logger.error(f"Failed to set hash {key}: {e}")
            return False
    
    async def get_hash(self, key: str) -> Dict[str, Any]:
        """Get all fields and values from a hash.
        
        Args:
            key: The hash key.
            
        Returns:
            Dictionary of field-value pairs (values are JSON-deserialized if possible).
        """
        try:
            raw_hash = await self.redis.hgetall(key)
            result = {}
            
            for field, value in raw_hash.items():
                try:
                    result[field] = loads(value)
                except (json.JSONDecodeError, TypeError):
                    result[field] = value
            
            return result
        except RedisError as e:
            logger.error(f"Failed to get hash {key}: {e}")
            return {}
    
    async def get_hash_field(self, key: str, field: str, default: Any = None) -> Any:
        """Get a single field from a hash.
        
        Args:
            key: The hash key.
            field: The field to get.
            default: Default value if field doesn't exist.
            
        Returns:
            The value (JSON-deserialized if possible) or default.
        """
        try:
            value = await self.redis.hget(key, field)
            if value is None:
                return default
            
            try:
                return loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        except RedisError as e:
            logger.error(f"Failed to get field {field} from hash {key}: {e}")
            return default
    
    async def add_to_set(self, key: str, *values: Any) -> int:
        """Add values to a set.
        
        Args:
            key: The set key.
            *values: Values to add (will be JSON-serialized if not strings).
            
        Returns:
            int: Number of values added.
        """
        try:
            serialized_values = []
            for value in values:
                if not isinstance(value, str):
                    serialized_values.append(dumps(value))
                else:
                    serialized_values.append(value)
            
            return await self.redis.sadd(key, *serialized_values)
        except (RedisError, TypeError) as e:
            logger.error(f"Failed to add values to set {key}: {e}")
            return 0
    
    async def get_set_members(self, key: str) -> List[Any]:
        """Get all members of a set.
        
        Args:
            key: The set key.
            
        Returns:
            List of values (JSON-deserialized if possible).
        """
        try:
            values = await self.redis.smembers(key)
            result = []
            
            for value in values:
                try:
                    result.append(loads(value))
                except (json.JSONDecodeError, TypeError):
                    result.append(value)
            
            return result
        except RedisError as e:
            logger.error(f"Failed to get members of set {key}: {e}")
            return []

    async def remove_from_set(self, key: str, *values: Any) -> int:
        """Remove values from a set.

        Args:
            key: The set key.
            *values: Values to remove (will be JSON-serialized if not strings).

        Returns:
            int: Number of values removed.
        """
        try:
            serialized_values = []
            for value in values:
                if not isinstance(value, str):
                    serialized_values.append(dumps(value))
                else:
                    serialized_values.append(value)

            return await self.redis.srem(key, *serialized_values)
        except (RedisError, TypeError) as e:
            logger.error(f"Failed to remove values from set {key}: {e}")
            return 0
    
    async def close(self) -> None:
        """Close the Redis connection."""
        if self.redis:
            await self.redis.close()
            logger.info("Redis connection closed")