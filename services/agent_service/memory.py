"""
Memory management for the Agent Service using Redis.
"""

import logging
import json
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

from shared.utils.redis_manager import RedisManager
from shared.utils.redis_client import RedisClient
from services.agent_service.models.state import AgentState, Memory, Message
from services.agent_service.models.config import MemoryConfig, AgentConfig
from services.agent_service.llm import call_llm

logger = logging.getLogger(__name__)


class MemoryManager:
    """Memory manager for the Agent Service."""
    
    # Redis key prefixes
    AGENT_STATE_KEY_PREFIX = "agent:state:"
    AGENT_MESSAGES_KEY_PREFIX = "agent:messages:"
    AGENT_MEMORY_KEY_PREFIX = "agent:memory:"
    AGENT_LONGTERM_KEY_PREFIX = "agent:longterm:"
    CONVERSATION_SUMMARY_KEY_PREFIX = "conversation:summary:"
    
    def __init__(self, redis_manager: Optional[RedisManager] = None):
        """Initialize the memory manager.
        
        Args:
            redis_manager: Optional Redis manager. A new one will be created if not provided.
        """
        self.redis_manager = redis_manager or RedisManager()
        self.redis = None
    
    async def initialize(self) -> None:
        """Initialize the memory manager."""
        if not self.redis_manager.redis_client:
            await self.redis_manager.connect()
        
        self.redis = self.redis_manager.redis_client
        logger.info("Memory manager initialized")
    
    async def save_agent_state(self, state: AgentState) -> bool:
        """Save the agent state to Redis.
        
        Args:
            state: The agent state to save.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        if not self.redis:
            await self.initialize()
        
        try:
            # Create state key
            state_key = f"{self.AGENT_STATE_KEY_PREFIX}{state.agent_id}:{state.conversation_id}"
            
            # Serialize state to dict
            state_dict = state.dict()
            
            # Update timestamp
            state_dict["updated_at"] = datetime.now().isoformat()
            
            # Save state to Redis
            await self.redis.set_value(state_key, state_dict)
            
            # Save messages separately for efficient access
            messages_key = f"{self.AGENT_MESSAGES_KEY_PREFIX}{state.conversation_id}"
            await self.redis.delete_key(messages_key)
            
            for message in state.messages:
                await self.redis.add_to_list(messages_key, message.dict())
            
            # Save memory separately
            memory_key = f"{self.AGENT_MEMORY_KEY_PREFIX}{state.agent_id}:{state.conversation_id}"
            await self.redis.set_value(memory_key, state.memory.dict())
            
            logger.info(f"Saved agent state for agent {state.agent_id}, conversation {state.conversation_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save agent state: {e}")
            return False
    
    async def load_agent_state(self, agent_id: str, conversation_id: str) -> Optional[AgentState]:
        """Load the agent state from Redis.
        
        Args:
            agent_id: The ID of the agent.
            conversation_id: The ID of the conversation.
            
        Returns:
            Optional[AgentState]: The agent state, or None if not found.
        """
        if not self.redis:
            await self.initialize()
        
        try:
            # Create state key
            state_key = f"{self.AGENT_STATE_KEY_PREFIX}{agent_id}:{conversation_id}"
            
            # Load state from Redis
            state_dict = await self.redis.get_value(state_key)
            
            if not state_dict:
                logger.warning(f"Agent state not found for agent {agent_id}, conversation {conversation_id}")
                return None
            
            # Create AgentState from dict
            return AgentState(**state_dict)
            
        except Exception as e:
            logger.error(f"Failed to load agent state: {e}")
            return None
    
    async def update_memory(
        self, 
        state: AgentState, 
        config: AgentConfig
    ) -> AgentState:
        """Update the agent's memory based on the current state and configuration.
        
        Args:
            state: The current agent state.
            config: The agent configuration.
            
        Returns:
            AgentState: The updated agent state.
        """
        if not self.redis:
            await self.initialize()
        
        try:
            # Check if we need to summarize the conversation
            if len(state.messages) >= config.memory.summarize_after:
                # Only summarize if there's no summary or if we've added enough new messages since the last summary
                if not state.memory.conversation_summary or len(state.messages) % config.memory.summarize_after == 0:
                    await self._summarize_conversation(state, config.memory)
            
            # Extract key facts if enabled
            if config.memory.key_fact_extraction_enabled:
                await self._extract_key_facts(state)
            
            # Update working memory with recent context
            state.memory.working = {
                "recent_messages": [msg.dict() for msg in state.messages[-5:] if msg.role != "system"],
                "recent_observations": state.observations[-3:] if state.observations else []
            }
            
            # Save memory to Redis
            memory_key = f"{self.AGENT_MEMORY_KEY_PREFIX}{state.agent_id}:{state.conversation_id}"
            await self.redis.set_value(memory_key, state.memory.dict())
            
            # Save long-term memory if enabled
            if config.memory.long_term_memory_enabled:
                longterm_key = f"{self.AGENT_LONGTERM_KEY_PREFIX}{state.agent_id}"
                
                # Keep track of conversations in long-term memory
                if "conversations" not in state.memory.long_term:
                    state.memory.long_term["conversations"] = []
                
                if conversation_id := state.conversation_id not in state.memory.long_term["conversations"]:
                    state.memory.long_term["conversations"].append(state.conversation_id)
                
                # Save long-term memory to Redis
                await self.redis.set_value(longterm_key, state.memory.long_term)
            
            logger.info(f"Updated memory for agent {state.agent_id}, conversation {state.conversation_id}")
            return state
            
        except Exception as e:
            logger.error(f"Failed to update memory: {e}")
            return state
    
    async def _summarize_conversation(self, state: AgentState, memory_config: MemoryConfig) -> None:
        """Summarize the conversation.
        
        Args:
            state: The current agent state.
            memory_config: The memory configuration.
        """
        try:
            # Get messages to summarize
            messages_to_summarize = state.messages[-memory_config.summarize_after:]
            
            # Format messages for the prompt
            formatted_messages = []
            for msg in messages_to_summarize:
                formatted_messages.append(f"{msg.role.upper()}: {msg.content}")
            
            messages_text = "\n\n".join(formatted_messages)
            
            # Create the prompt
            system_prompt = "You are an AI assistant that creates concise, informative summaries of conversations. Focus on capturing the main points, questions, and information exchanged."
            user_prompt = f"Please summarize the following conversation segment. Focus on the key information, questions, and decisions.\n\nCONVERSATION:\n{messages_text}"
            
            # Call LLM to get summary
            llm_response = await call_llm(
                messages=[{"role": "user", "content": user_prompt}],
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=300
            )
            
            # Extract summary
            if "error" in llm_response:
                logger.error(f"Error generating summary: {llm_response['error']}")
                return
            
            new_summary = llm_response.get("content", "")
            
            # Create or update the summary
            if state.memory.conversation_summary:
                state.memory.conversation_summary += f"\n\nContinued:\n{new_summary}"
            else:
                state.memory.conversation_summary = new_summary
            
            # Save summary to Redis
            summary_key = f"{self.CONVERSATION_SUMMARY_KEY_PREFIX}{state.conversation_id}"
            await self.redis.set_value(summary_key, state.memory.conversation_summary)
            
            logger.info(f"Generated conversation summary for conversation {state.conversation_id}")
        
        except Exception as e:
            logger.error(f"Failed to summarize conversation: {e}")
    
    async def _extract_key_facts(self, state: AgentState) -> None:
        """Extract key facts from recent messages.
        
        Args:
            state: The current agent state.
        """
        try:
            # Get recent messages to extract facts from
            recent_messages = state.messages[-5:]
            
            # Format messages for the prompt
            formatted_messages = []
            for msg in recent_messages:
                formatted_messages.append(f"{msg.role.upper()}: {msg.content}")
            
            messages_text = "\n\n".join(formatted_messages)
            
            # Create the prompt
            system_prompt = "You are an AI assistant that extracts key facts from conversations. Focus on identifying important information that should be remembered for future reference."
            user_prompt = f"""Please extract 1-3 key facts from the following conversation segment that would be important to remember for future interactions. 
            Focus on specific information like names, preferences, goals, or important context.
            Format each fact as a simple, clear statement.
            
            CONVERSATION:
            {messages_text}
            
            KEY FACTS (1-3 facts only):"""
            
            # Call LLM to extract facts
            llm_response = await call_llm(
                messages=[{"role": "user", "content": user_prompt}],
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=200
            )
            
            # Extract facts
            if "error" in llm_response:
                logger.error(f"Error extracting key facts: {llm_response['error']}")
                return
            
            facts_text = llm_response.get("content", "")
            
            # Parse facts (assuming one fact per line)
            new_facts = [line.strip() for line in facts_text.split("\n") if line.strip()]
            
            # Add new facts to the list, avoiding duplicates
            for fact in new_facts:
                # Remove any leading numbers or bullets
                clean_fact = fact
                for prefix in ["- ", "• ", "* ", "1. ", "2. ", "3. ", "4. ", "5. "]:
                    if clean_fact.startswith(prefix):
                        clean_fact = clean_fact[len(prefix):]
                        break
                
                # Check if this fact or a very similar one is already in the list
                if clean_fact and clean_fact not in state.memory.key_facts:
                    state.memory.key_facts.append(clean_fact)
            
            logger.info(f"Extracted key facts for conversation {state.conversation_id}")
        
        except Exception as e:
            logger.error(f"Failed to extract key facts: {e}")
    
    async def get_conversation_history(self, conversation_id: str) -> List[Message]:
        """Get the conversation history from Redis.
        
        Args:
            conversation_id: The ID of the conversation.
            
        Returns:
            List[Message]: The conversation history.
        """
        if not self.redis:
            await self.initialize()
        
        try:
            # Create messages key
            messages_key = f"{self.AGENT_MESSAGES_KEY_PREFIX}{conversation_id}"
            
            # Load messages from Redis
            messages_data = await self.redis.get_list(messages_key)
            
            # Create Message objects
            messages = []
            for msg_data in messages_data:
                messages.append(Message(**msg_data))
            
            return messages
            
        except Exception as e:
            logger.error(f"Failed to get conversation history: {e}")
            return []
    
    async def get_memory(self, agent_id: str, conversation_id: str) -> Memory:
        """Get the agent's memory from Redis.
        
        Args:
            agent_id: The ID of the agent.
            conversation_id: The ID of the conversation.
            
        Returns:
            Memory: The agent's memory.
        """
        if not self.redis:
            await self.initialize()
        
        try:
            # Create memory key
            memory_key = f"{self.AGENT_MEMORY_KEY_PREFIX}{agent_id}:{conversation_id}"
            
            # Load memory from Redis
            memory_data = await self.redis.get_value(memory_key)
            
            if not memory_data:
                # Create new memory
                return Memory()
            
            # Create Memory object
            return Memory(**memory_data)
            
        except Exception as e:
            logger.error(f"Failed to get memory: {e}")
            return Memory()
    
    async def delete_agent_state(self, agent_id: str, conversation_id: str) -> bool:
        """Delete the agent state from Redis.
        
        Args:
            agent_id: The ID of the agent.
            conversation_id: The ID of the conversation.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        if not self.redis:
            await self.initialize()
        
        try:
            # Create keys
            state_key = f"{self.AGENT_STATE_KEY_PREFIX}{agent_id}:{conversation_id}"
            messages_key = f"{self.AGENT_MESSAGES_KEY_PREFIX}{conversation_id}"
            memory_key = f"{self.AGENT_MEMORY_KEY_PREFIX}{agent_id}:{conversation_id}"
            summary_key = f"{self.CONVERSATION_SUMMARY_KEY_PREFIX}{conversation_id}"
            
            # Delete keys
            await self.redis.delete_key(state_key)
            await self.redis.delete_key(messages_key)
            await self.redis.delete_key(memory_key)
            await self.redis.delete_key(summary_key)
            
            logger.info(f"Deleted agent state for agent {agent_id}, conversation {conversation_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete agent state: {e}")
            return False