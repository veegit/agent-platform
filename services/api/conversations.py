"""
Conversation management for the API service.
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any

from shared.utils.redis_manager import RedisManager
from shared.utils.redis_conversation_store import RedisConversationStore
from services.api.models.conversation import (
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
    ConversationSummary
)
from services.api.clients.agent_service_client import AgentServiceClient
from services.api.clients.agent_lifecycle_client import AgentLifecycleClient

logger = logging.getLogger(__name__)


class ConversationService:
    """Service for managing conversations."""
    
    def __init__(
        self,
        redis_manager: Optional[RedisManager] = None,
        agent_service_client: Optional[AgentServiceClient] = None,
        agent_lifecycle_client: Optional[AgentLifecycleClient] = None
    ):
        """Initialize the conversation service.
        
        Args:
            redis_manager: Optional Redis manager. A new one will be created if not provided.
            agent_service_client: Optional agent service client. A new one will be created if not provided.
            agent_lifecycle_client: Optional agent lifecycle client. A new one will be created if not provided.
        """
        self.redis_manager = redis_manager or RedisManager()
        self.conversation_store = None
        self.agent_service = agent_service_client or AgentServiceClient()
        self.agent_lifecycle = agent_lifecycle_client or AgentLifecycleClient()
    
    async def initialize(self) -> None:
        """Initialize the service."""
        if not self.redis_manager.conversations:
            await self.redis_manager.connect()
            
        self.conversation_store = self.redis_manager.conversations
        logger.info("Conversation service initialized")
    
    async def start_conversation(
        self,
        agent_id: str,
        user_id: str,
        initial_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Start a new conversation with an agent.
        
        Args:
            agent_id: The ID of the agent to start a conversation with.
            user_id: The ID of the user starting the conversation.
            initial_message: Optional initial message to send.
            metadata: Optional metadata about the conversation.
            
        Returns:
            Dict[str, Any]: The conversation data with agent response.
        """
        if not self.conversation_store:
            await self.initialize()
        
        try:
            # Check if the agent exists and is active
            agent_status = await self.agent_lifecycle.get_agent_status(agent_id)
            
            if not agent_status or not agent_status.get("is_available", False):
                return {
                    "error": f"Agent {agent_id} is not available for conversations"
                }
            
            # Create a new conversation
            conversation_id = str(uuid.uuid4())
            now = datetime.now().isoformat()
            
            conversation_data = {
                "id": conversation_id,
                "agent_id": agent_id,
                "user_id": user_id,
                "status": ConversationStatus.ACTIVE.value,
                "created_at": now,
                "updated_at": now,
                "metadata": metadata or {}
            }
            
            # Create conversation in Redis
            await self.conversation_store.create_conversation(user_id, agent_id, metadata)
            
            # If there's an initial message, send it
            if initial_message:
                # Add the message to the conversation
                message_id = await self.conversation_store.add_message(
                    conversation_id=conversation_id,
                    role=MessageRole.USER.value,
                    content=initial_message,
                    metadata={}
                )
                
                # Send the message to the agent service
                response = await self.agent_service.send_message(
                    agent_id=agent_id,
                    user_id=user_id,
                    message=initial_message,
                    conversation_id=conversation_id
                )
                
                if "error" in response:
                    return {
                        "error": response["error"],
                        "conversation_id": conversation_id
                    }
                
                # Add the agent's response to the conversation
                if "message" in response:
                    agent_message = response["message"]
                    await self.conversation_store.add_message(
                        conversation_id=conversation_id,
                        role=agent_message.get("role", MessageRole.AGENT.value),
                        content=agent_message.get("content", ""),
                        metadata=agent_message.get("metadata", {})
                    )
            
            # Get the conversation with messages
            conversation = await self.get_conversation(conversation_id)
            
            # Create a proper response structure
            return {
                "id": conversation_id,
                "agent_id": agent_id,
                "user_id": user_id,
                "status": ConversationStatus.ACTIVE.value,
                "messages": conversation.get("messages", []),
                "created_at": conversation.get("created_at", now),
                "updated_at": conversation.get("updated_at", now),
                "metadata": metadata or {}
            }
        
        except Exception as e:
            logger.error(f"Error starting conversation: {e}")
            return {
                "error": f"Failed to start conversation: {str(e)}"
            }
    
    async def send_message(
        self,
        conversation_id: str,
        content: str,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Send a message in a conversation.
        
        Args:
            conversation_id: The ID of the conversation.
            content: The message content.
            user_id: The ID of the user sending the message.
            metadata: Optional metadata.
            
        Returns:
            Dict[str, Any]: The response data with agent's reply.
        """
        if not self.conversation_store:
            await self.initialize()
        
        try:
            # Get the conversation
            conversation = await self.get_conversation(conversation_id)
            
            if not conversation:
                return {
                    "error": f"Conversation {conversation_id} not found"
                }
            
            # Check if the conversation is active
            if conversation.get("status") != ConversationStatus.ACTIVE.value:
                return {
                    "error": f"Conversation {conversation_id} is not active"
                }
            
            # Check if the user is part of the conversation
            if conversation.get("user_id") != user_id:
                return {
                    "error": f"User {user_id} is not part of conversation {conversation_id}"
                }
            
            # Add the message to the conversation
            message_id = await self.conversation_store.add_message(
                conversation_id=conversation_id,
                role=MessageRole.USER.value,
                content=content,
                metadata=metadata or {}
            )
            
            # Send the message to the agent service
            agent_id = conversation.get("agent_id")
            response = await self.agent_service.send_message(
                agent_id=agent_id,
                user_id=user_id,
                message=content,
                conversation_id=conversation_id
            )
            
            if "error" in response:
                return {
                    "error": response["error"],
                    "message_id": message_id
                }
            
            # Add the agent's response to the conversation
            agent_message = None
            if "message" in response:
                agent_message = response["message"]
                await self.conversation_store.add_message(
                    conversation_id=conversation_id,
                    role=agent_message.get("role", MessageRole.AGENT.value),
                    content=agent_message.get("content", ""),
                    metadata=agent_message.get("metadata", {})
                )
            
            # Create a proper response structure
            return {
                "conversation_id": conversation_id,
                "user_message": {
                    "id": message_id,
                    "role": MessageRole.USER.value,
                    "content": content,
                    "timestamp": datetime.now().isoformat(),
                    "metadata": metadata or {}
                },
                "agent_message": agent_message
            }
        
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return {
                "error": f"Failed to send message: {str(e)}"
            }
    
    async def get_conversation(self, conversation_id: str) -> Dict[str, Any]:
        """Get a conversation by ID.
        
        Args:
            conversation_id: The ID of the conversation.
            
        Returns:
            Dict[str, Any]: The conversation data.
        """
        if not self.conversation_store:
            await self.initialize()
        
        try:
            # Get the conversation from Redis
            conversation_data = await self.conversation_store.get_conversation(conversation_id)
            
            if not conversation_data:
                return {}
            
            return conversation_data
            
        except Exception as e:
            logger.error(f"Error getting conversation {conversation_id}: {e}")
            return {}
    
    async def list_conversations(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        status: Optional[ConversationStatus] = None,
        skip: int = 0,
        limit: int = 100
    ) -> Dict[str, Any]:
        """List conversations.
        
        Args:
            user_id: Optional user ID to filter by.
            agent_id: Optional agent ID to filter by.
            status: Optional status to filter by.
            skip: Number of conversations to skip.
            limit: Maximum number of conversations to return.
            
        Returns:
            Dict[str, Any]: The conversations data.
        """
        if not self.conversation_store:
            await self.initialize()
        
        try:
            # Get the conversation IDs based on filters
            conversation_ids = []
            
            if user_id:
                user_conversations = await self.conversation_store.get_user_conversations(user_id)
                conversation_ids.extend(user_conversations)
            
            if agent_id:
                agent_conversations = await self.conversation_store.get_agent_conversations(agent_id)
                # If both user_id and agent_id are provided, we want the intersection
                if user_id:
                    conversation_ids = [id for id in conversation_ids if id in agent_conversations]
                else:
                    conversation_ids.extend(agent_conversations)
            
            # If no filters were applied, we'll need to get all conversations
            # (in a real implementation, this would need pagination)
            if not user_id and not agent_id:
                # This is a placeholder; the actual implementation would vary
                # For MVP, assume a limited number of conversations
                pass
            
            # Get the conversations
            conversations = []
            for conv_id in conversation_ids:
                conv = await self.get_conversation(conv_id)
                if conv and (not status or conv.get("status") == status.value):
                    # Convert to a summary format
                    messages = conv.get("messages", [])
                    messages_count = len(messages)
                    last_message_timestamp = None
                    if messages:
                        last_message = messages[-1]
                        last_message_timestamp = last_message.get("timestamp")
                    
                    conversations.append({
                        "id": conv.get("id"),
                        "agent_id": conv.get("agent_id"),
                        "user_id": conv.get("user_id"),
                        "title": conv.get("metadata", {}).get("title"),
                        "last_message_timestamp": last_message_timestamp,
                        "status": conv.get("status"),
                        "message_count": messages_count,
                        "created_at": conv.get("created_at"),
                        "updated_at": conv.get("updated_at")
                    })
            
            # Sort by last message timestamp (newest first)
            conversations.sort(
                key=lambda c: c.get("last_message_timestamp") or c.get("updated_at") or c.get("created_at"),
                reverse=True
            )
            
            # Apply pagination
            paginated_conversations = conversations[skip:skip+limit]
            
            return {
                "conversations": paginated_conversations,
                "total": len(conversations)
            }
            
        except Exception as e:
            logger.error(f"Error listing conversations: {e}")
            return {
                "conversations": [],
                "total": 0
            }
    
    async def get_conversation_messages(
        self,
        conversation_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Get messages from a conversation.
        
        Args:
            conversation_id: The ID of the conversation.
            skip: Number of messages to skip.
            limit: Maximum number of messages to return.
            
        Returns:
            Dict[str, Any]: The messages data.
        """
        if not self.conversation_store:
            await self.initialize()
        
        try:
            # Get the conversation
            conversation = await self.get_conversation(conversation_id)
            
            if not conversation:
                return {
                    "error": f"Conversation {conversation_id} not found",
                    "messages": [],
                    "total": 0
                }
            
            # Get the messages
            messages = conversation.get("messages", [])
            
            # Apply pagination
            paginated_messages = messages[skip:skip+limit]
            
            return {
                "conversation_id": conversation_id,
                "messages": paginated_messages,
                "total": len(messages)
            }
            
        except Exception as e:
            logger.error(f"Error getting conversation messages: {e}")
            return {
                "error": f"Failed to get conversation messages: {str(e)}",
                "messages": [],
                "total": 0
            }