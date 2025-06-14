"""
Redis Manager for handling connections and providing access to all Redis stores.
"""

import logging
import asyncio
from typing import Optional

from shared.utils.redis_client import RedisClient
from shared.utils.redis_agent_store import RedisAgentStore
from shared.utils.redis_conversation_store import RedisConversationStore
from shared.utils.redis_skill_store import RedisSkillStore
from shared.utils.redis_delegation_store import RedisDelegationStore

logger = logging.getLogger(__name__)

class RedisManager:
    """Redis Manager for handling connections and providing access to all Redis stores."""
    
    # Singleton instance
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        """Create a new instance of RedisManager if it doesn't exist."""
        if not cls._instance:
            cls._instance = super(RedisManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, host: str = None, port: int = None, db: int = None, password: str = None):
        """Initialize the Redis manager.
        
        Args:
            host: Redis host.
            port: Redis port.
            db: Redis db.
            password: Redis password.
        """
        if self._initialized:
            return
        
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        
        self.redis_client = None
        self.agent_store = None
        self.conversation_store = None
        self.skill_store = None
        self.delegation_store = None
        
        self._max_retries = 5
        self._retry_delay = 1  # seconds
        self._health_check_interval = 30  # seconds
        self._health_check_task = None
        
        self._initialized = True
    
    async def connect(self) -> bool:
        """Connect to Redis and initialize all stores.
        
        Returns:
            bool: True if successful, False otherwise.
        """
        for attempt in range(1, self._max_retries + 1):
            try:
                logger.info(f"Attempting to connect to Redis (attempt {attempt}/{self._max_retries})...")
                
                # Create Redis client
                self.redis_client = RedisClient(
                    host=self.host,
                    port=self.port,
                    db=self.db,
                    password=self.password
                )
                
                # Test connection
                if not await self.redis_client.ping():
                    raise ConnectionError("Failed to ping Redis")
                
                # Initialize stores
                self.agent_store = RedisAgentStore(self.redis_client)
                self.conversation_store = RedisConversationStore(self.redis_client)
                self.skill_store = RedisSkillStore(self.redis_client)
                self.delegation_store = RedisDelegationStore(self.redis_client)
                
                # Start health check
                self._start_health_check()
                
                logger.info("Successfully connected to Redis")
                return True
                
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                
                if attempt < self._max_retries:
                    logger.info(f"Retrying in {self._retry_delay} seconds...")
                    await asyncio.sleep(self._retry_delay)
                    # Exponential backoff
                    self._retry_delay *= 2
                else:
                    logger.error("Max retries reached, failed to connect to Redis")
                    return False
    
    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        self._stop_health_check()
        
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None
            self.agent_store = None
            self.conversation_store = None
            self.skill_store = None
            self.delegation_store = None
            
            logger.info("Disconnected from Redis")
    
    def _start_health_check(self) -> None:
        """Start Redis health check."""
        if self._health_check_task:
            self._stop_health_check()
        
        self._health_check_task = asyncio.create_task(self._health_check_loop())
    
    def _stop_health_check(self) -> None:
        """Stop Redis health check."""
        if self._health_check_task:
            self._health_check_task.cancel()
            self._health_check_task = None
    
    async def _health_check_loop(self) -> None:
        """Health check loop."""
        try:
            while True:
                await asyncio.sleep(self._health_check_interval)
                
                try:
                    if not await self.redis_client.ping():
                        logger.warning("Redis health check failed, attempting to reconnect...")
                        await self.connect()
                    else:
                        logger.debug("Redis health check passed")
                except Exception as e:
                    logger.error(f"Error during Redis health check: {e}")
                    await self.connect()
        except asyncio.CancelledError:
            logger.info("Redis health check stopped")
    
    @property
    def agents(self) -> Optional[RedisAgentStore]:
        """Get the agent store.
        
        Returns:
            Optional[RedisAgentStore]: The agent store or None if not connected.
        """
        return self.agent_store
    
    @property
    def conversations(self) -> Optional[RedisConversationStore]:
        """Get the conversation store.
        
        Returns:
            Optional[RedisConversationStore]: The conversation store or None if not connected.
        """
        return self.conversation_store
    
    @property
    def skills(self) -> Optional[RedisSkillStore]:
        """Get the skill store.

        Returns:
            Optional[RedisSkillStore]: The skill store or None if not connected.
        """
        return self.skill_store

    @property
    def delegations(self) -> Optional[RedisDelegationStore]:
        """Get the delegation store."""
        return self.delegation_store
