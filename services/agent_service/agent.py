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
from services.agent_service.llm import call_llm

logger = logging.getLogger(__name__)


class Agent:
    """Agent implementation for the Agent Service."""
    
    def __init__(
        self,
        config: AgentConfig,
        memory_manager: Optional[MemoryManager] = None,
        skill_client: Optional[SkillServiceClient] = None,
        delegations: Optional[Dict[str, Dict[str, Any]]] = None,
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
        self.delegations = delegations or {}

        logger.info(f"Initialized agent {config.agent_id} with name '{config.persona.name}'")

    async def _determine_domain(self, user_message: str) -> Optional[str]:
        """Use the reasoning model to choose a delegation domain."""
        if not self.delegations:
            return None

        domains = ", ".join(self.delegations.keys())
        system_prompt = (
            "You are a supervisor agent deciding which domain expert should handle a user question. "
            f"Available domains: {domains}. "
            "Return the best domain in a JSON object with a 'domain' field."
        )

        schema = {"type": "object", "properties": {"domain": {"type": "string"}}, "required": ["domain"]}

        try:
            result = await call_llm(
                [{"role": "user", "content": user_message}],
                model=self.config.reasoning_model,
                system_prompt=system_prompt,
                output_schema=schema,
            )
            domain = (result.get("domain") or result.get("content") or "").strip().strip(". ").lower()
            if domain:
                return domain
        except Exception as e:
            logger.error(f"Failed to determine domain via LLM: {e}")

        return None
    
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

        # If this agent is a supervisor, use the reasoning model to choose a delegation domain
        if self.config.is_supervisor and self.delegations:
            matched_agent: Optional[Agent] = None

            domain = await self._determine_domain(user_message)
            if domain and domain in self.delegations:
                candidate = self.delegations[domain].get("agent")
                if candidate and candidate.config.skills:
                    matched_agent = candidate
                    logger.info(
                        f"Delegating message about {domain} to {candidate.config.agent_id}"
                    )
                else:
                    logger.info(
                        f"Agent for domain {domain} unavailable or lacks skills, falling back"
                    )

            if not matched_agent and "general" in self.delegations:
                matched_agent = self.delegations["general"].get("agent")
                if matched_agent:
                    logger.info(
                        f"Delegating message to general agent {matched_agent.config.agent_id}"
                    )

            if matched_agent:
                return await matched_agent.process_message(user_message, user_id, conversation_id)

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
        
        # Execute the graph - use ainvoke instead of invoke for LangGraph 0.0.15
        try:
            # Try with ainvoke method first (newer LangGraph versions)
            if hasattr(self.graph, 'ainvoke'):
                final_state = await self.graph.ainvoke(state.dict())
            else:
                # Fall back to invoke for older versions
                final_state = await self.graph.invoke(state.dict())
        except Exception as e:
            logger.error(f"Error executing agent graph: {e}")
            # Add a fallback response if graph execution fails
            state.messages.append(Message(
                id=str(uuid.uuid4()),
                role=MessageRole.AGENT,
                content="I'm sorry, I'm having trouble processing your request right now. Please try again later.",
                timestamp=datetime.now()
            ))
            return AgentOutput(
                message=state.messages[-1],
                state=state
            )
        
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
