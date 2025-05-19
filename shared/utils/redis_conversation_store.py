"""
Redis client module for handling conversation data in Redis.
Provides functions for storing and retrieving conversation histories.
"""

import json
import logging
from typing import Any, Dict, List, Optional
import uuid
from datetime import datetime

from shared.utils.redis_client import RedisClient

logger = logging.getLogger(__name__)

class RedisConversationStore:
    """Redis client for handling conversation data in Redis."""
    
    # Redis key prefixes
    CONVERSATION_KEY_PREFIX = "conversation:"
    CONVERSATION_MESSAGES_KEY_PREFIX = "conversation:messages:"
    CONVERSATION_AGENT_INDEX_PREFIX = "agent:conversations:"
    CONVERSATION_USER_INDEX_PREFIX = "user:conversations:"
    ALL_CONVERSATIONS_KEY = "conversations:all"
    
    def __init__(self, redis_client: Optional[RedisClient] = None):
        """Initialize the Redis conversation store.
        
        Args:
            redis_client: Optional Redis client. If not provided, a new one will be created.
        """
        self.redis = redis_client or RedisClient()
    
    async def create_conversation(self, user_id: str, agent_id: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Create a new conversation.
        
        Args:
            user_id: User ID.
            agent_id: Agent ID.
            metadata: Optional metadata.
            
        Returns:
            str: Conversation ID.
        """
        conversation_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        conversation_data = {
            "id": conversation_id,
            "agent_id": agent_id,
            "user_id": user_id,
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "metadata": metadata or {}
        }
        
        conversation_key = f"{self.CONVERSATION_KEY_PREFIX}{conversation_id}"
        
        try:
            # Store the conversation data
            await self.redis.set_hash(conversation_key, conversation_data)
            
            # Add to agent's conversations set
            agent_conversations_key = f"{self.CONVERSATION_AGENT_INDEX_PREFIX}{agent_id}"
            await self.redis.add_to_set(agent_conversations_key, conversation_id)
            
            # Add to user's conversations set
            user_conversations_key = f"{self.CONVERSATION_USER_INDEX_PREFIX}{user_id}"
            await self.redis.add_to_set(user_conversations_key, conversation_id)
            
            # Add to all conversations set
            await self.redis.add_to_set(self.ALL_CONVERSATIONS_KEY, conversation_id)
            
            logger.info(f"Created conversation {conversation_id} between user {user_id} and agent {agent_id}")
            return conversation_id
            
        except Exception as e:
            logger.error(f"Failed to create conversation: {e}")
            raise
    
    async def add_message(self, conversation_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Add a message to a conversation.
        
        Args:
            conversation_id: Conversation ID.
            role: Message role ("user" or "agent").
            content: Message content.
            metadata: Optional metadata.
            
        Returns:
            str: Message ID.
        """
        message_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        message_data = {
            "id": message_id,
            "role": role,
            "content": content,
            "timestamp": now,
            "metadata": metadata or {}
        }
        
        conversation_messages_key = f"{self.CONVERSATION_MESSAGES_KEY_PREFIX}{conversation_id}"
        conversation_key = f"{self.CONVERSATION_KEY_PREFIX}{conversation_id}"
        
        try:
            # Add message to the conversation's message list
            await self.redis.add_to_list(conversation_messages_key, message_data)
            
            # Update the conversation's updated_at timestamp
            await self.redis.set_hash(conversation_key, {"updated_at": now})
            
            logger.info(f"Added message {message_id} to conversation {conversation_id}")
            return message_id
            
        except Exception as e:
            logger.error(f"Failed to add message to conversation {conversation_id}: {e}")
            raise
    
    async def get_messages(self, conversation_id: str, start: int = 0, end: int = -1) -> List[Dict[str, Any]]:
        """Get messages from a conversation.
        
        Args:
            conversation_id: Conversation ID.
            start: Start index (0-based, inclusive).
            end: End index (0-based, inclusive). -1 means the last message.
            
        Returns:
            List[Dict[str, Any]]: List of messages.
        """
        conversation_messages_key = f"{self.CONVERSATION_MESSAGES_KEY_PREFIX}{conversation_id}"
        
        try:
            # Get messages from the list
            messages = await self.redis.get_list(conversation_messages_key)
            
            # Apply slicing
            return messages[start:None if end == -1 else end + 1]
            
        except Exception as e:
            logger.error(f"Failed to get messages from conversation {conversation_id}: {e}")
            return []
    
    async def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Get conversation data.
        
        Args:
            conversation_id: Conversation ID.
            
        Returns:
            Optional[Dict[str, Any]]: Conversation data or None if not found.
        """
        conversation_key = f"{self.CONVERSATION_KEY_PREFIX}{conversation_id}"
        conversation_messages_key = f"{self.CONVERSATION_MESSAGES_KEY_PREFIX}{conversation_id}"
        
        try:
            # Get conversation data
            conversation_data = await self.redis.get_hash(conversation_key)
            if not conversation_data:
                return None
            
            # Get messages
            messages = await self.redis.get_list(conversation_messages_key)
            conversation_data["messages"] = messages
            
            return conversation_data
            
        except Exception as e:
            logger.error(f"Failed to get conversation {conversation_id}: {e}")
            return None
    
    async def update_conversation_status(self, conversation_id: str, status: str) -> bool:
        """Update conversation status.
        
        Args:
            conversation_id: Conversation ID.
            status: New status ("active", "completed", etc.).
            
        Returns:
            bool: True if successful, False otherwise.
        """
        conversation_key = f"{self.CONVERSATION_KEY_PREFIX}{conversation_id}"
        now = datetime.now().isoformat()
        
        try:
            # Update status and updated_at
            await self.redis.set_hash(conversation_key, {
                "status": status,
                "updated_at": now
            })
            
            logger.info(f"Updated status of conversation {conversation_id} to {status}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update status of conversation {conversation_id}: {e}")
            return False
    
    async def get_user_conversations(self, user_id: str) -> List[str]:
        """Get conversation IDs for a user.
        
        Args:
            user_id: User ID.
            
        Returns:
            List[str]: List of conversation IDs.
        """
        user_conversations_key = f"{self.CONVERSATION_USER_INDEX_PREFIX}{user_id}"
        
        try:
            return await self.redis.get_set_members(user_conversations_key)
            
        except Exception as e:
            logger.error(f"Failed to get conversations for user {user_id}: {e}")
            return []
    
    async def get_agent_conversations(self, agent_id: str) -> List[str]:
        """Get conversation IDs for an agent.
        
        Args:
            agent_id: Agent ID.
            
        Returns:
            List[str]: List of conversation IDs.
        """
        agent_conversations_key = f"{self.CONVERSATION_AGENT_INDEX_PREFIX}{agent_id}"
        
        try:
            return await self.redis.get_set_members(agent_conversations_key)
            
        except Exception as e:
            logger.error(f"Failed to get conversations for agent {agent_id}: {e}")
            return []
    
    async def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation.
        
        Args:
            conversation_id: Conversation ID.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            # Get conversation data first to get user and agent IDs
            conversation_data = await self.get_conversation(conversation_id)
            if not conversation_data:
                return False
            
            user_id = conversation_data.get("user_id")
            agent_id = conversation_data.get("agent_id")
            
            # Delete conversation data
            conversation_key = f"{self.CONVERSATION_KEY_PREFIX}{conversation_id}"
            await self.redis.delete_key(conversation_key)
            
            # Delete messages
            conversation_messages_key = f"{self.CONVERSATION_MESSAGES_KEY_PREFIX}{conversation_id}"
            await self.redis.delete_key(conversation_messages_key)
            
            # Remove from user's conversations set
            if user_id:
                user_conversations_key = f"{self.CONVERSATION_USER_INDEX_PREFIX}{user_id}"
                await self.redis.delete_key(user_conversations_key)
            
            # Remove from agent's conversations set
            if agent_id:
                agent_conversations_key = f"{self.CONVERSATION_AGENT_INDEX_PREFIX}{agent_id}"
                await self.redis.delete_key(agent_conversations_key)
            
            # Remove from all conversations set
            await self.redis.delete_key(self.ALL_CONVERSATIONS_KEY)
            
            logger.info(f"Deleted conversation {conversation_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete conversation {conversation_id}: {e}")
            return False