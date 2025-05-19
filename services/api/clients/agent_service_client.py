"""
Client for communicating with the Agent Service.
"""

import logging
import os
import json
import httpx
from datetime import datetime
from typing import Any, Dict, List, Optional

from services.api.models.conversation import (
    Message,
    MessageRole,
    ConversationStatus,
    Conversation
)

logger = logging.getLogger(__name__)


class AgentServiceClient:
    """Client for communicating with the Agent Service."""
    
    def __init__(self, base_url: Optional[str] = None):
        """Initialize the agent service client.
        
        Args:
            base_url: The base URL of the agent service. Defaults to environment variable.
        """
        self.base_url = base_url or os.environ.get("AGENT_SERVICE_URL", "http://localhost:8003")
        logger.info(f"Initialized Agent Service client with base URL: {self.base_url}")
    
    async def send_message(
        self,
        agent_id: str,
        user_id: str,
        message: str,
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send a message to an agent and get a response.
        
        Args:
            agent_id: The ID of the agent to send the message to.
            user_id: The ID of the user sending the message.
            message: The message content.
            conversation_id: Optional ID of the conversation. A new one will be created if not provided.
            
        Returns:
            Dict[str, Any]: The response data.
        """
        try:
            request_data = {
                "user_id": user_id,
                "message": message,
                "conversation_id": conversation_id
            }
            
            logger.info(f"Sending message to agent {agent_id}: {message[:50]}{'...' if len(message) > 50 else ''}")
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/agents/{agent_id}/chat",
                    json=request_data,
                    timeout=60.0  # Longer timeout for agent processing
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Agent service request failed: {response.status_code} - {response.text}")
                    return {
                        "error": f"Agent service request failed: {response.status_code}"
                    }
                
        except Exception as e:
            logger.error(f"Error sending message to agent: {e}")
            return {
                "error": f"Failed to communicate with agent service: {str(e)}"
            }
    
    async def get_conversation_history(
        self,
        agent_id: str,
        conversation_id: str
    ) -> List[Message]:
        """Get the conversation history.
        
        Args:
            agent_id: The ID of the agent.
            conversation_id: The ID of the conversation.
            
        Returns:
            List[Message]: The conversation history.
        """
        try:
            logger.info(f"Getting conversation history for agent {agent_id}, conversation {conversation_id}")
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/agents/{agent_id}/conversations/{conversation_id}/history",
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    # Convert the response data to Message objects
                    messages_data = response.json()
                    messages = []
                    
                    for msg_data in messages_data:
                        # Ensure timestamp is in datetime format
                        timestamp = msg_data.get("timestamp")
                        if isinstance(timestamp, str):
                            try:
                                timestamp = datetime.fromisoformat(timestamp)
                            except ValueError:
                                timestamp = datetime.now()
                        
                        messages.append(Message(
                            id=msg_data.get("id"),
                            role=msg_data.get("role"),
                            content=msg_data.get("content"),
                            timestamp=timestamp,
                            metadata=msg_data.get("metadata")
                        ))
                    
                    return messages
                else:
                    logger.error(f"Failed to get conversation history: {response.status_code} - {response.text}")
                    return []
                
        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return []