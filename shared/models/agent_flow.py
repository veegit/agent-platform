"""
Models for tracking agent flow and execution paths.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class FlowNodeType(str, Enum):
    """Type of node in the agent flow."""
    
    AGENT = "agent"
    SKILL = "skill"
    REASONING = "reasoning"
    DELEGATION = "delegation"


class FlowNode(BaseModel):
    """Represents a single node in the agent execution flow."""
    
    id: str = Field(..., description="Unique identifier for this flow node")
    type: FlowNodeType = Field(..., description="Type of the flow node")
    name: str = Field(..., description="Display name of the node")
    description: Optional[str] = Field(default=None, description="Description of what this node does")
    timestamp: datetime = Field(..., description="When this node was executed")
    duration_ms: Optional[int] = Field(default=None, description="Execution duration in milliseconds")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")


class FlowEdge(BaseModel):
    """Represents a connection between two nodes in the agent flow."""
    
    from_node: str = Field(..., description="ID of the source node")
    to_node: str = Field(..., description="ID of the target node")
    label: Optional[str] = Field(default=None, description="Label for the edge")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")


class AgentFlow(BaseModel):
    """Complete agent execution flow for a message."""
    
    message_id: str = Field(..., description="ID of the message this flow belongs to")
    conversation_id: str = Field(..., description="ID of the conversation")
    user_id: str = Field(..., description="ID of the user")
    root_agent_id: str = Field(..., description="ID of the root agent that handled the message")
    nodes: List[FlowNode] = Field(default_factory=list, description="List of nodes in the flow")
    edges: List[FlowEdge] = Field(default_factory=list, description="List of edges connecting the nodes")
    start_time: datetime = Field(..., description="When the flow execution started")
    end_time: Optional[datetime] = Field(default=None, description="When the flow execution completed")
    total_duration_ms: Optional[int] = Field(default=None, description="Total execution duration in milliseconds")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")


class FlowTracker:
    """Helper class for tracking agent flow during execution."""
    
    def __init__(self, message_id: str, conversation_id: str, user_id: str, root_agent_id: str):
        self.flow = AgentFlow(
            message_id=message_id,
            conversation_id=conversation_id,
            user_id=user_id,
            root_agent_id=root_agent_id,
            start_time=datetime.utcnow()
        )
        self._node_counter = 0
    
    def add_node(
        self, 
        node_type: FlowNodeType, 
        name: str, 
        description: Optional[str] = None,
        duration_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Add a new node to the flow and return its ID."""
        node_id = f"node_{self._node_counter}"
        self._node_counter += 1
        
        node = FlowNode(
            id=node_id,
            type=node_type,
            name=name,
            description=description,
            timestamp=datetime.utcnow(),
            duration_ms=duration_ms,
            metadata=metadata
        )
        
        self.flow.nodes.append(node)
        return node_id
    
    def add_edge(
        self, 
        from_node: str, 
        to_node: str, 
        label: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add an edge between two nodes."""
        edge = FlowEdge(
            from_node=from_node,
            to_node=to_node,
            label=label,
            metadata=metadata
        )
        self.flow.edges.append(edge)
    
    def complete(self) -> AgentFlow:
        """Mark the flow as complete and return the final flow."""
        self.flow.end_time = datetime.utcnow()
        if self.flow.start_time and self.flow.end_time:
            duration = self.flow.end_time - self.flow.start_time
            self.flow.total_duration_ms = int(duration.total_seconds() * 1000)
        return self.flow
