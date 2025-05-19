"""
Agent implementation for the Agent Service.
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

from services.agent_service.models.state import (
    AgentState,
    Message,
    MessageRole,
    AgentOutput
)
from services.agent_service.models.config import AgentConfig
from services.agent_service.memory import MemoryManager
from services.agent_service.skill_client import SkillServiceClient
from services.agent_service.graph import create_agent_graph, process_reasoning_output

logger = logging.getLogger(__name__)


class Agent:
    """Agent implementation for the Agent Service."""
    
    def __init__(
        self,
        config: AgentConfig,
        memory_manager: Optional[MemoryManager] = None,
        skill_client: Optional[SkillServiceClient] = None
    ):
        """Initialize the agent.
        
        Args:
            config: The agent configuration.
            memory_manager: Optional memory manager. A new one will be created if not provided.
            skill_client: Optional skill service client. A new one will be created if not provided.
        """
        self.config = config
        self.memory_manager = memory_manager or MemoryManager()
        self.skill_client = skill_client or SkillServiceClient()
        self.graph = create_agent_graph(config, skill_client)
        
        logger.info(f"Initialized agent {config.agent_id} with name '{config.persona.name}'")
    
    async def initialize(self) -> None:
        """Initialize the agent's dependencies."""
        await self.memory_manager.initialize()
        logger.info(f"Agent {self.config.agent_id} initialized")
    
    async def process_message(
        self,
        user_message: str,
        user_id: str,
        conversation_id: Optional[str] = None
    ) -> AgentOutput:
        """Process a user message and generate a response.
        
        Args:
            user_message: The user's message.
            user_id: The ID of the user.
            conversation_id: Optional ID of the conversation. A new one will be created if not provided.
            
        Returns:
            AgentOutput: The agent's output.
        """
        logger.info(f"Processing message for agent {self.config.agent_id}")
        
        # Generate conversation ID if not provided
        conversation_id = conversation_id or str(uuid.uuid4())
        
        # Try to load existing state or create a new one
        state = await self.memory_manager.load_agent_state(self.config.agent_id, conversation_id)
        
        if not state:
            # Create a new state
            state = AgentState(
                agent_id=self.config.agent_id,
                conversation_id=conversation_id,
                user_id=user_id,
                messages=[]
            )
            
            # Add system message
            system_message = Message(
                id=str(uuid.uuid4()),
                role=MessageRole.SYSTEM,
                content=self.config.persona.system_prompt,
                timestamp=datetime.now()
            )
            
            state.messages.append(system_message)
            
            # Load memory or create new if not found
            state.memory = await self.memory_manager.get_memory(self.config.agent_id, conversation_id)
        
        # Add user message to the state
        user_message_obj = Message(
            id=str(uuid.uuid4()),
            role=MessageRole.USER,
            content=user_message,
            timestamp=datetime.now()
        )
        
        state.messages.append(user_message_obj)
        
        # Update memory
        state = await self.memory_manager.update_memory(state, self.config)
        
        # Save state
        await self.memory_manager.save_agent_state(state)
        
        # Execute the graph
        final_state = await self.graph.invoke(state.dict())
        
        # Convert the final state back to an AgentState
        final_agent_state = AgentState(**final_state)
        
        # Get the agent's response (last message)
        agent_message = final_agent_state.messages[-1]
        
        # Update memory again with the final state
        final_agent_state = await self.memory_manager.update_memory(final_agent_state, self.config)
        
        # Save the final state
        await self.memory_manager.save_agent_state(final_agent_state)
        
        # Return the output
        return AgentOutput(
            message=agent_message,
            state=final_agent_state
        )
    
    async def get_conversation_history(self, conversation_id: str) -> List[Message]:
        """Get the conversation history.
        
        Args:
            conversation_id: The ID of the conversation.
            
        Returns:
            List[Message]: The conversation history.
        """
        return await self.memory_manager.get_conversation_history(conversation_id)