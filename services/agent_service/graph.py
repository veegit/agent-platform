"""
State graph definition for the Agent Service.
"""

import logging
from typing import Dict, Any, Optional, List, Union, Literal, TypedDict

from langgraph.graph import StateGraph, END
from langgraph.graph.nodes import Node

from services.agent_service.models.state import (
    AgentState,
    ReasoningOutput,
    SkillExecutionOutput,
    ResponseFormulationOutput,
    SkillExecution
)
from services.agent_service.models.config import AgentConfig
from services.agent_service.nodes.reasoning import reasoning_node
from services.agent_service.nodes.skill_execution import skill_execution_node
from services.agent_service.nodes.response_formulation import response_formulation_node
from services.agent_service.skill_client import SkillServiceClient

logger = logging.getLogger(__name__)


class AgentStateDict(TypedDict):
    """Dictionary representation of agent state for LangGraph."""
    
    agent_id: str
    conversation_id: str
    user_id: str
    messages: List[Dict[str, Any]]
    memory: Dict[str, Any]
    current_node: Optional[str]
    current_skill: Optional[Dict[str, Any]]
    skill_results: List[Dict[str, Any]]
    thought_process: List[str]
    observations: List[str]
    plan: List[str]
    created_at: str
    updated_at: str
    error: Optional[str]


# Node implementations with proper parameters
class ReasoningNode(Node):
    """Reasoning node for the agent state graph."""
    
    def __init__(self, config: AgentConfig, skill_client: SkillServiceClient):
        """Initialize the reasoning node.
        
        Args:
            config: The agent configuration.
            skill_client: The skill service client.
        """
        self.config = config
        self.skill_client = skill_client
    
    async def invoke(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the reasoning node.
        
        Args:
            state: The current agent state as a dictionary.
            
        Returns:
            Dict[str, Any]: The updated state.
        """
        # Convert dict to AgentState
        agent_state = AgentState(**state)
        
        # Get available skills
        available_skills = await self.skill_client.get_available_skills()
        
        # Execute reasoning
        result = await reasoning_node(agent_state, self.config, available_skills)
        
        # Return the updated state
        return result.state.dict()


class SkillExecutionNode(Node):
    """Skill execution node for the agent state graph."""
    
    def __init__(self, skill_client: SkillServiceClient):
        """Initialize the skill execution node.
        
        Args:
            skill_client: The skill service client.
        """
        self.skill_client = skill_client
    
    async def invoke(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the skill execution node.
        
        Args:
            state: The current agent state as a dictionary.
            
        Returns:
            Dict[str, Any]: The updated state.
        """
        # Convert dict to AgentState
        agent_state = AgentState(**state)
        
        # Execute skill
        result = await skill_execution_node(agent_state, self.skill_client)
        
        # Return the updated state
        return result.state.dict()


class ResponseFormulationNode(Node):
    """Response formulation node for the agent state graph."""
    
    def __init__(self, config: AgentConfig):
        """Initialize the response formulation node.
        
        Args:
            config: The agent configuration.
        """
        self.config = config
    
    async def invoke(self, state: Dict[str, Any], direct_response: Optional[str] = None) -> Dict[str, Any]:
        """Execute the response formulation node.
        
        Args:
            state: The current agent state as a dictionary.
            direct_response: Optional direct response to use.
            
        Returns:
            Dict[str, Any]: The updated state.
        """
        # Convert dict to AgentState
        agent_state = AgentState(**state)
        
        # Formulate response
        result = await response_formulation_node(agent_state, self.config, direct_response)
        
        # Return the updated state
        return result.state.dict()


def should_use_skill(state: Dict[str, Any]) -> Literal["skill_execution", "response_formulation"]:
    """Conditional router to determine if a skill should be used.
    
    Args:
        state: The current agent state.
        
    Returns:
        Literal["skill_execution", "response_formulation"]: The next node to execute.
    """
    # Reasoning output must have set current_skill in the state if we should use a skill
    if state.get("current_skill") is not None:
        return "skill_execution"
    else:
        return "response_formulation"


def create_agent_graph(
    config: AgentConfig,
    skill_client: Optional[SkillServiceClient] = None
) -> StateGraph:
    """Create the agent state graph.
    
    Args:
        config: The agent configuration.
        skill_client: Optional skill service client. A new one will be created if not provided.
        
    Returns:
        StateGraph: The agent state graph.
    """
    # Create skill client if not provided
    skill_client = skill_client or SkillServiceClient()
    
    # Create nodes
    reasoning = ReasoningNode(config, skill_client)
    skill_execution = SkillExecutionNode(skill_client)
    response_formulation = ResponseFormulationNode(config)
    
    # Create state graph
    workflow = StateGraph(AgentStateDict)
    
    # Add nodes
    workflow.add_node("reasoning", reasoning)
    workflow.add_node("skill_execution", skill_execution)
    workflow.add_node("response_formulation", response_formulation)
    
    # Define edges
    workflow.add_edge("reasoning", should_use_skill)
    workflow.add_edge("skill_execution", "response_formulation")
    workflow.add_edge("response_formulation", END)
    
    # Compile the graph
    return workflow.compile()


def process_reasoning_output(
    reasoning_output: ReasoningOutput,
    state: AgentState
) -> AgentState:
    """Process the output from the reasoning node.
    
    Args:
        reasoning_output: The output from the reasoning node.
        state: The current agent state.
        
    Returns:
        AgentState: The updated agent state.
    """
    # Update state with reasoning output
    state.thought_process.append(reasoning_output.thoughts)
    
    # Check if we should use a skill
    if reasoning_output.skill_to_use and not reasoning_output.should_respond_directly:
        # Set current skill in state
        state.current_skill = SkillExecution(
            skill_id=reasoning_output.skill_to_use.skill_id,
            parameters=reasoning_output.skill_to_use.parameters,
            agent_id=state.agent_id,
            conversation_id=state.conversation_id
        )
    else:
        # Clear current skill if we're responding directly
        state.current_skill = None
    
    return state