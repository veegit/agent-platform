# CLAUDE.md - Agentic Platform MVP Development Guide

## Project Overview

This project is an MVP for an agentic platform with the following core components:
1. Agent Lifecycle Service
2. Agent Service
3. Skill Service
4. Redis for experiential memory
5. Simple API layer for user interactions

## Development Standards

### Technology Stack
- Python 3.11+
- LangGraph for agent workflow orchestration
- FastAPI for API endpoints
- Redis for memory storage and state management
- LangChain for some skill integrations

### Coding Standards
- Use type hints throughout the codebase
- Create modular components
- Follow PEP 8 conventions
- Use async/await pattern where appropriate for API endpoints

### Project Structure
```
agentic-platform/
├── services/
│   ├── agent_lifecycle/
│   ├── agent_service/
│   ├── skill_service/
│   └── api/
├── shared/
│   ├── models/
│   ├── utils/
│   └── config/
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## Implementation Details

### Core Service Models

#### Agent Model
```python
class Agent:
    agent_id: str  # Unique identifier
    name: str  # Human-readable name
    description: str  # Purpose description
    status: str  # "active", "inactive", etc.
    skills: List[str]  # Skill IDs the agent can use
    config: Dict[str, Any]  # Configuration parameters
```

#### Skill Model
```python
class Skill:
    skill_id: str  # Unique identifier
    name: str  # Human-readable name
    description: str  # What the skill does
    parameters: List[Dict]  # Required and optional parameters
    response_format: Dict  # Expected response structure
```

#### Conversation Model
```python
class Message:
    id: str
    role: str  # "user" or "agent"
    content: str
    timestamp: datetime
    metadata: Dict[str, Any]  # Optional metadata

class Conversation:
    id: str
    agent_id: str
    user_id: str
    messages: List[Message]
    status: str  # "active", "completed", etc.
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any]  # Optional metadata
```

### LangGraph Implementation

Use LangGraph for implementing agent workflows. LangGraph helps create structured, stateful agent workflows, particularly suitable for this MVP. Specifically:

1. Define agent state and transitions
2. Create nodes for different agent operations (reasoning, skill execution, etc.)
3. Define the graph structure connecting these nodes
4. Handle conversation context and memory integration

## Service Implementation Guidelines

### 1. Agent Lifecycle Service

Create a service that manages agent registration and status. Implement:

- Agent creation/registration
- Status management (activate/deactivate)
- Configuration storage in Redis
- Simple validation for agent configuration

Use FastAPI for the REST endpoints and Redis for storage. Keep interfaces minimal but sufficient to demonstrate core functionality.

### 2. Agent Service

Implement the core agent runtime with LangGraph. Create:

- A reasoning node that determines actions based on user input
- A skill execution node that calls the Skill Service
- A response formulation node that creates user-facing messages
- State management that tracks conversation context

Focus on a simple but effective reasoning approach for MVP - don't overengineer the cognitive architecture.

### 3. Skill Service

Create a simple skill registry and execution service:

- Implement basic skill registration
- Create skill validation logic
- Develop execution framework
- Implement three core skills:
  - web-search: Use a simple wrapper around a search API using SerpAPI using the following API private key MY_API_KEY
  - summarize-text: Use Claude
  - ask-follow-up: Generate follow-up questions based on context

### 4. Redis Integration

Use Redis for all stateful data:

- Agent configurations
- Active conversations
- Working memory for agents
- Skill execution results

Define clear Redis key structures and data formats. Use Redis data types appropriately (Hashes, Lists, Sets, etc.).

### 5. API Layer

Create a simple but complete API layer with FastAPI:

- User authentication (simplified for MVP)
- Conversation management
- Message sending/receiving
- Agent status queries

## Implementation Sequence

1. Set up the project structure and shared components
2. Implement Redis integration and basic data models
3. Create the Skill Service with 2-3 example skills
4. Develop the Agent Service with LangGraph workflows
5. Implement the Agent Lifecycle service
6. Create the API layer
7. Build a simple frontend (optional for MVP)

## Development Tips

1. Use a local Redis instance for development
2. Create small, focused services that communicate via well-defined APIs
3. Use environment variables for configuration
4. Log agent actions and skill executions for debugging
5. Implement proper error handling from the beginning

## LangGraph-Specific Guidance

When implementing the agent workflow with LangGraph:

1. Use the `StateGraph` class to create the agent's state machine
2. Define clear states like "receiving_input", "reasoning", "executing_skill", "formulating_response"
3. Create typed state classes to maintain type safety
4. Implement conditional edges for dynamic agent behavior
5. Use the async API for better performance
6. Leverage LangGraph's memory interfaces for maintaining context

Example LangGraph structure:
```python
from langgraph.graph import StateGraph
from pydantic import BaseModel, Field

# Define state
class AgentState(BaseModel):
    messages: List[Message] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)
    current_skill: Optional[str] = None
    skill_results: List[Dict] = Field(default_factory=list)
    
# Create nodes
def reasoning(state: AgentState) -> AgentState:
    # Determine next actions
    # ...
    return updated_state

def execute_skill(state: AgentState) -> AgentState:
    # Call skill service
    # ...
    return updated_state

def formulate_response(state: AgentState) -> AgentState:
    # Create response for user
    # ...
    return updated_state

# Build graph
graph = StateGraph(AgentState)
graph.add_node("reasoning", reasoning)
graph.add_node("execute_skill", execute_skill)
graph.add_node("formulate_response", formulate_response)

# Add edges
graph.add_edge("reasoning", "execute_skill")
graph.add_edge("execute_skill", "formulate_response")
graph.add_edge("formulate_response", "reasoning")

# Conditional branching
def should_execute_skill(state: AgentState) -> str:
    if state.current_skill:
        return "execute_skill"
    return "formulate_response"

graph.add_conditional_edges("reasoning", should_execute_skill, 
                           {"execute_skill": "execute_skill", 
                            "formulate_response": "formulate_response"})

# Compile the graph
agent_executor = graph.compile()
```

## Testing

For the MVP, no unit tests or other tests are required to reduce token consumption


## Deployment

For the MVP, a simple local deployment is sufficient. 

## Documentation

For the MVP, No need to document in detail, keep is simple to reduce token consumption.

