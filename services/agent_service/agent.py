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
from shared.models.agent_flow import FlowTracker, FlowNodeType

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
        # Track which delegate is handling each conversation
        self.conversation_delegates: Dict[str, Agent] = {}

        logger.info(f"Initialized agent {config.agent_id} with name '{config.persona.name}'")

    async def _analyze_query_complexity(self, user_message: str) -> Dict[str, Any]:
        """Analyze if a query requires multiple agents and which domains are needed."""
        if not self.delegations:
            return {"is_complex": False, "domains": [], "strategy": "single"}

        # Build detailed domain descriptions
        domain_descriptions = []
        for domain, delegation_info in self.delegations.items():
            agent = delegation_info.get("agent")
            if agent and hasattr(agent, 'config'):
                agent_name = agent.config.persona.name
                agent_desc = agent.config.persona.description
                skills = ", ".join(agent.config.skills) if agent.config.skills else "no specific skills"
                domain_descriptions.append(
                    f"- {domain}: {agent_name} - {agent_desc} (Skills: {skills})"
                )
            else:
                domain_descriptions.append(f"- {domain}: General purpose domain")
        
        domains_text = "\n".join(domain_descriptions)
        system_prompt = (
            "You are a supervisor agent analyzing whether a user question requires multiple domain experts. "
            "Available domains and their capabilities:\n"
            f"{domains_text}\n\n"
            "Analyze the user's question and determine:"
            "1. Is this a complex query that would benefit from multiple domain experts?"
            "2. Which domains would be needed to provide a comprehensive answer?"
            "3. What strategy should be used?"
            "\n"
            "For example:"
            "- Stock analysis questions might need both 'finance' (for current data) and 'research' (for market analysis)"
            "- Technical questions might need multiple specialized domains"
            "- Simple questions typically need only one domain"
            "\n"
            "Return JSON with:"
            "- 'is_complex': boolean (true if multiple domains needed)"
            "- 'domains': list of domain names needed (in order of execution)"
            "- 'strategy': 'single' for one agent, 'sequential' for multiple agents in order, 'parallel' for simultaneous execution"
            "- 'reasoning': brief explanation of the analysis"
        )

        schema = {
            "type": "object",
            "properties": {
                "is_complex": {"type": "boolean"},
                "domains": {"type": "array", "items": {"type": "string"}},
                "strategy": {"type": "string", "enum": ["single", "sequential", "parallel"]},
                "reasoning": {"type": "string"}
            },
            "required": ["is_complex", "domains", "strategy", "reasoning"]
        }

        try:
            result = await call_llm(
                [{"role": "user", "content": user_message}],
                model=self.config.reasoning_model,
                system_prompt=system_prompt,
                output_schema=schema,
            )

            logger.info(f"Query complexity analysis for '{user_message}': {result}")
            
            # Validate domains exist
            valid_domains = [d for d in result.get("domains", []) if d in self.delegations]
            result["domains"] = valid_domains
            
            return result
        except Exception as e:
            logger.error(f"Failed to analyze query complexity: {e}")
            return {"is_complex": False, "domains": [], "strategy": "single"}

    async def _determine_domain(self, user_message: str) -> Optional[str]:
        """Use the reasoning model to choose a delegation domain (legacy single-agent method)."""
        if not self.delegations:
            return None

        # Build detailed domain descriptions
        domain_descriptions = []
        for domain, delegation_info in self.delegations.items():
            agent = delegation_info.get("agent")
            if agent and hasattr(agent, 'config'):
                agent_name = agent.config.persona.name
                agent_desc = agent.config.persona.description
                skills = ", ".join(agent.config.skills) if agent.config.skills else "no specific skills"
                domain_descriptions.append(
                    f"- {domain}: {agent_name} - {agent_desc} (Skills: {skills})"
                )
            else:
                domain_descriptions.append(f"- {domain}: General purpose domain")
        
        domains_text = "\n".join(domain_descriptions)
        system_prompt = (
            "You are a supervisor agent deciding which domain expert should handle a user question. "
            "Available domains and their capabilities:\n"
            f"{domains_text}\n\n"
            "Choose the most appropriate domain based on the user's question. "
            "Consider what type of expertise or skills would be needed to answer the question effectively. "
            "Return the domain name in JSON as {'domain': '<name>'}. "
            "If none of the specialized domains apply, respond with {'domain': 'general'}."
        )

        schema = {"type": "object", "properties": {"domain": {"type": "string"}}, "required": ["domain"]}

        try:
            result = await call_llm(
                [{"role": "user", "content": user_message}],
                model=self.config.reasoning_model,
                system_prompt=system_prompt,
                output_schema=schema,
            )

            logger.info(f"Calling LLM with user_message='{user_message}', system_prompt='{system_prompt}' and it returned: {result}")
            
            # Handle error responses from LLM
            if "error" in result or "fallback" in result:
                logger.warning(f"LLM returned error/fallback response: {result}")
                return None
            
            domain = result.get("domain")
            if domain and domain in self.delegations:
                logger.info(f"LLM suggested domain '{domain}'")
                return domain
            elif domain == "general":
                logger.info(f"LLM suggested general domain, will handle directly")
                return None  # Handle directly instead of delegating
            elif domain:
                logger.info(f"LLM suggested unknown domain '{domain}', will handle directly")
                return None  # Handle directly instead of failing
        except Exception as e:
            logger.error(f"Failed to determine domain via LLM: {e}")

        return None

    async def _coordinate_multiple_agents(self, user_message: str, domains: List[str], strategy: str, flow_tracker: FlowTracker, root_node_id: str, user_id: str, conversation_id: str) -> AgentOutput:
        """Coordinate multiple agents to handle a complex query."""
        logger.info(f"Coordinating multiple agents for domains: {domains} with strategy: {strategy}")
        
        agent_results = []
        
        if strategy == "sequential":
            # Execute agents in sequence, passing context between them
            context = user_message
            
            for i, domain in enumerate(domains):
                if domain not in self.delegations:
                    continue
                    
                agent = self.delegations[domain].get("agent")
                if not agent:
                    continue
                
                # Create specific query for this agent
                if i == 0:
                    # First agent gets the original query
                    agent_query = context
                else:
                    # Subsequent agents get context from previous results
                    previous_results = "\n".join([f"From {r['domain']}: {r['content']}" for r in agent_results])
                    agent_query = f"Original question: {user_message}\n\nPrevious analysis:\n{previous_results}\n\nPlease provide additional analysis for the {domain} domain."
                
                # Add delegation node
                delegation_node_id = flow_tracker.add_node(
                    FlowNodeType.DELEGATION,
                    f"Delegate to {domain.title()} (Step {i+1})",
                    f"Sequential delegation to {agent.config.persona.name} for {domain} domain",
                    metadata={"domain": domain, "target_agent_id": agent.config.agent_id, "step": i+1}
                )
                flow_tracker.add_edge(root_node_id, delegation_node_id, "coordinates")
                
                # Add target agent node
                target_agent_node_id = flow_tracker.add_node(
                    FlowNodeType.AGENT,
                    agent.config.persona.name,
                    f"Specialized agent for {domain} domain (Step {i+1})",
                    metadata={"agent_id": agent.config.agent_id, "domain": domain, "step": i+1}
                )
                flow_tracker.add_edge(delegation_node_id, target_agent_node_id, "executes")
                
                # Execute agent
                try:
                    result = await agent.process_message(agent_query, user_id, conversation_id)
                    agent_results.append({
                        "domain": domain,
                        "agent_name": agent.config.persona.name,
                        "content": result.message.content,
                        "step": i+1
                    })
                    logger.info(f"Agent {domain} completed step {i+1}")
                except Exception as e:
                    logger.error(f"Error executing agent {domain}: {e}")
                    agent_results.append({
                        "domain": domain,
                        "agent_name": agent.config.persona.name,
                        "content": f"Error: Could not get response from {domain} agent",
                        "step": i+1
                    })
        
        elif strategy == "parallel":
            # Execute agents in parallel (for future implementation)
            # For now, fall back to sequential
            return await self._coordinate_multiple_agents(user_message, domains, "sequential", flow_tracker, root_node_id, user_id, conversation_id)
        
        # Synthesize results from all agents
        return await self._synthesize_agent_results(user_message, agent_results, flow_tracker, root_node_id, user_id, conversation_id)
    
    async def _synthesize_agent_results(self, original_query: str, agent_results: List[Dict[str, Any]], flow_tracker: FlowTracker, root_node_id: str, user_id: str, conversation_id: str) -> AgentOutput:
        """Synthesize results from multiple agents into a comprehensive response."""
        logger.info(f"Synthesizing results from {len(agent_results)} agents")
        
        # Add synthesis node
        synthesis_node_id = flow_tracker.add_node(
            FlowNodeType.REASONING,
            "Result Synthesis",
            "Synthesizing responses from multiple domain experts",
            metadata={"agent_count": len(agent_results)}
        )
        flow_tracker.add_edge(root_node_id, synthesis_node_id, "synthesizes")
        
        # Prepare synthesis prompt
        results_text = "\n\n".join([
            f"**{result['agent_name']} ({result['domain']} domain):**\n{result['content']}"
            for result in agent_results
        ])
        
        synthesis_prompt = (
            f"You are a supervisor agent synthesizing responses from multiple domain experts. "
            f"The user asked: '{original_query}'\n\n"
            f"Here are the responses from different domain experts:\n\n{results_text}\n\n"
            f"Please provide a comprehensive, well-structured response that:"
            f"1. Integrates insights from all domain experts"
            f"2. Addresses the user's original question completely"
            f"3. Highlights key findings and connections between different aspects"
            f"4. Provides a clear, actionable conclusion"
            f"\n\nFormat your response in a clear, professional manner."
        )
        
        try:
            synthesis_result = await call_llm(
                [{"role": "user", "content": synthesis_prompt}],
                model=self.config.reasoning_model,
                system_prompt="You are a helpful supervisor agent that synthesizes information from domain experts to provide comprehensive answers."
            )
            
            synthesized_content = synthesis_result if isinstance(synthesis_result, str) else str(synthesis_result)
            
        except Exception as e:
            logger.error(f"Error synthesizing results: {e}")
            # Fallback: concatenate results
            synthesized_content = f"Based on analysis from multiple domain experts:\n\n{results_text}"
        
        # Create final response
        response_message = Message(
            id=str(uuid.uuid4()),
            role=MessageRole.AGENT,
            content=synthesized_content,
            timestamp=datetime.now()
        )
        
        # Create state for the response
        state = AgentState(
            agent_id=self.config.agent_id,
            conversation_id=conversation_id,
            user_id=user_id,
            messages=[response_message]
        )
        
        # Complete the flow and add it to the response
        completed_flow = flow_tracker.complete()
        response_message.agent_flow = completed_flow.dict()
        
        return AgentOutput(message=response_message, state=state)
    
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
        
        # Initialize flow tracker
        message_id = str(uuid.uuid4())
        flow_tracker = FlowTracker(
            message_id=message_id,
            conversation_id=conversation_id,
            user_id=user_id,
            root_agent_id=self.config.agent_id
        )
        
        # Add root agent node
        root_node_id = flow_tracker.add_node(
            FlowNodeType.AGENT,
            self.config.persona.name,
            f"Root agent processing user message",
            metadata={"agent_id": self.config.agent_id, "is_supervisor": self.config.is_supervisor}
        )

        logger.info(f"is_supervisor:{self.config.is_supervisor}, delegations:{self.delegations}, conversation_id:{conversation_id}, conversation_delegates: {self.conversation_delegates}")
        
        # If this agent is a supervisor, analyze query complexity and coordinate agents
        if self.config.is_supervisor and self.delegations:
            # Analyze if this query requires multiple agents
            complexity_analysis = await self._analyze_query_complexity(user_message)
            
            logger.info(f"Query complexity analysis: {complexity_analysis}")
            
            if complexity_analysis.get("is_complex") and len(complexity_analysis.get("domains", [])) > 1:
                # Handle complex queries with multiple agents
                domains = complexity_analysis["domains"]
                strategy = complexity_analysis["strategy"]
                
                logger.info(f"Coordinating multiple agents for complex query: domains={domains}, strategy={strategy}")
                
                return await self._coordinate_multiple_agents(
                    user_message, domains, strategy, flow_tracker, root_node_id, user_id, conversation_id
                )
            
            else:
                # Handle simple queries with single agent (existing logic)
                matched_agent: Optional[Agent] = None
                
                # Use complexity analysis result if available, otherwise fall back to legacy method
                if complexity_analysis.get("domains"):
                    domain = complexity_analysis["domains"][0]
                else:
                    domain = await self._determine_domain(user_message)
                
                if domain and domain in self.delegations:
                    candidate = self.delegations[domain].get("agent")
                    if candidate and candidate.config.skills:
                        matched_agent = candidate
                        logger.info(
                            f"Delegating message about {domain} to {candidate.config.agent_id}"
                        )
                        
                        # Add delegation node to flow
                        delegation_node_id = flow_tracker.add_node(
                            FlowNodeType.DELEGATION,
                            f"Delegate to {domain.title()}",
                            f"Delegating to {candidate.config.persona.name} for {domain} domain",
                            metadata={"domain": domain, "target_agent_id": candidate.config.agent_id}
                        )
                        flow_tracker.add_edge(root_node_id, delegation_node_id, "delegates to")
                        
                        # Add target agent node
                        target_agent_node_id = flow_tracker.add_node(
                            FlowNodeType.AGENT,
                            candidate.config.persona.name,
                            f"Specialized agent for {domain} domain",
                            metadata={"agent_id": candidate.config.agent_id, "domain": domain}
                        )
                        flow_tracker.add_edge(delegation_node_id, target_agent_node_id, "executes")
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
                        
                        # Add general delegation node to flow
                        delegation_node_id = flow_tracker.add_node(
                            FlowNodeType.DELEGATION,
                            "Delegate to General",
                            f"Delegating to {matched_agent.config.persona.name} for general handling",
                            metadata={"domain": "general", "target_agent_id": matched_agent.config.agent_id}
                        )
                        flow_tracker.add_edge(root_node_id, delegation_node_id, "delegates to")
                        
                        # Add target agent node
                        target_agent_node_id = flow_tracker.add_node(
                            FlowNodeType.AGENT,
                            matched_agent.config.persona.name,
                            "General purpose agent",
                            metadata={"agent_id": matched_agent.config.agent_id, "domain": "general"}
                        )
                        flow_tracker.add_edge(delegation_node_id, target_agent_node_id, "executes")

                if matched_agent:
                    # Store delegate for future turns
                    self.conversation_delegates[conversation_id] = matched_agent
                    
                    # Process message with delegated agent and pass flow tracker
                    result = await matched_agent.process_message(user_message, user_id, conversation_id)
                    
                    # Complete the flow and add it to the result
                    completed_flow = flow_tracker.complete()
                    result.message.agent_flow = completed_flow.dict()
                    
                    return result
        
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
        
        # Add reasoning node to flow
        reasoning_node_id = flow_tracker.add_node(
            FlowNodeType.REASONING,
            "Reasoning",
            "Agent reasoning and decision making",
            metadata={"agent_id": self.config.agent_id}
        )
        flow_tracker.add_edge(root_node_id, reasoning_node_id, "processes")
        
        # Execute the graph - use ainvoke instead of invoke for LangGraph 0.0.15
        try:
            # Try with ainvoke method first (newer LangGraph versions)
            if hasattr(self.graph, 'ainvoke'):
                final_state = await self.graph.ainvoke(state.dict())
            else:
                # Fall back to invoke for older versions
                final_state = await self.graph.invoke(state.dict())
                
            # Track skill executions from the final state
            if 'skill_results' in final_state and final_state['skill_results']:
                last_reasoning_node = reasoning_node_id
                for skill_result in final_state['skill_results']:
                    if isinstance(skill_result, dict) and 'skill_id' in skill_result:
                        skill_node_id = flow_tracker.add_node(
                            FlowNodeType.SKILL,
                            skill_result.get('skill_name', skill_result['skill_id']),
                            f"Executed skill: {skill_result.get('skill_name', skill_result['skill_id'])}",
                            metadata={
                                "skill_id": skill_result['skill_id'],
                                "status": skill_result.get('status', 'unknown')
                            }
                        )
                        flow_tracker.add_edge(last_reasoning_node, skill_node_id, "executes")
                        last_reasoning_node = skill_node_id
                        
        except Exception as e:
            logger.error(f"Error executing agent graph: {e}")
            # Add a fallback response if graph execution fails
            state.messages.append(Message(
                id=str(uuid.uuid4()),
                role=MessageRole.AGENT,
                content="I'm sorry, I'm having trouble processing your request right now. Please try again later.",
                timestamp=datetime.now()
            ))
            
            # Complete the flow even on error
            completed_flow = flow_tracker.complete()
            state.messages[-1].agent_flow = completed_flow.dict()
            
            return AgentOutput(
                message=state.messages[-1],
                state=state
            )
        
        # Convert the final state back to an AgentState
        final_agent_state = AgentState(**final_state)
        
        # Get the agent's response (last message)
        agent_message = final_agent_state.messages[-1]
        
        # Complete the flow tracking
        completed_flow = flow_tracker.complete()
        
        # Add flow data to the agent message
        agent_message.agent_flow = completed_flow.dict()
        
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
