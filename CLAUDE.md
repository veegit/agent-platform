# CLAUDE.md - Agentic Platform Development Guide

## Project Overview

This is a fully-featured agentic platform with the following core components:
1. **Agent Lifecycle Service** - Manages agent registration, configuration, and delegation
2. **Agent Service** - Runs agent workflows using LangGraph
3. **Skill Service** - Registry and execution engine for agent skills
4. **API Service** - User-facing REST API for conversations and management
5. **Redis** - State management, memory, and inter-service communication

## Technology Stack

- **Python 3.11+** with type hints throughout
- **LangGraph 0.0.15** for agent workflow orchestration
- **FastAPI** for all API endpoints
- **Redis 7** for state management and memory
- **Google Gemini API** for LLM capabilities
- **SerpAPI** for web search functionality
- **Alpha Vantage API** for financial data
- **Docker & Docker Compose** for deployment

## Project Structure

```
agent-platform/
├── services/
│   ├── agent_lifecycle/        # Agent registration & delegation
│   │   ├── main.py
│   │   ├── router.py
│   │   ├── repository.py
│   │   └── models/agent.py
│   ├── agent_service/          # LangGraph agent runtime
│   │   ├── main.py
│   │   ├── agent.py
│   │   ├── graph.py            # LangGraph workflow
│   │   ├── llm.py
│   │   ├── memory.py
│   │   ├── skill_client.py
│   │   ├── models/
│   │   │   ├── state.py        # Agent state models
│   │   │   └── config.py
│   │   └── nodes/              # LangGraph nodes
│   │       ├── reasoning.py
│   │       ├── skill_execution.py
│   │       └── response_formulation.py
│   ├── skill_service/          # Skill registry & execution
│   │   ├── main.py
│   │   ├── router.py
│   │   ├── registry.py
│   │   ├── executor.py
│   │   ├── validator.py
│   │   └── skills/
│   │       ├── web_search.py
│   │       ├── summarize_text.py
│   │       ├── ask_follow_up.py
│   │       └── finance.py
│   └── api/                    # Main API layer
│       ├── main.py
│       ├── router.py
│       ├── conversations.py
│       ├── models/
│       └── clients/
├── shared/
│   ├── models/
│   │   ├── skill.py
│   │   └── agent_flow.py       # Flow tracking
│   ├── utils/
│   │   ├── redis_client.py
│   │   ├── redis_agent_store.py
│   │   ├── redis_conversation_store.py
│   │   ├── redis_skill_store.py
│   │   ├── redis_delegation_store.py
│   │   └── json_utils.py
│   └── config/
├── tests/                      # Comprehensive test suite
├── frontend/                   # Simple web UI
├── main.py                     # Unified service launcher
├── bootstrap.sh               # Agent setup script
├── azure-deploy.sh           # Azure deployment
└── docker-compose.yml        # Multi-service deployment
```

## Core Models

### Agent Configuration
```python
class AgentConfig(BaseModel):
    agent_id: str
    persona: PersonaConfig          # Name, description, goals, constraints
    llm: LLMConfig                 # Model, temperature, max_tokens
    skills: List[str]              # Available skill IDs
    memory: MemoryConfig           # Memory settings
    is_supervisor: bool = False    # Delegation capability
```

### Agent State (LangGraph)
```python
class AgentState(BaseModel):
    agent_id: str
    conversation_id: str
    user_id: str
    messages: List[Message]
    memory: Memory                 # Long-term & working memory
    current_skill: Optional[SkillExecution]
    skill_results: List[SkillResult]
    thought_process: List[str]     # Agent reasoning
    observations: List[str]
    plan: List[str]
```

### Skills
Available skills with full implementations:
- **web-search**: SerpAPI integration for web searches
- **summarize-text**: Text summarization using Gemini
- **ask-follow-up**: Context-based follow-up question generation  
- **finance**: Stock price data via Alpha Vantage API

## LangGraph Implementation

The platform uses LangGraph for sophisticated agent workflows:

### State Graph Structure
```python
# services/agent_service/graph.py
workflow = StateGraph(AgentStateDict)
workflow.add_node("reasoning", reasoning_node)
workflow.add_node("skill_execution", skill_execution_node)
workflow.add_node("response_formulation", response_formulation_node)

# Conditional routing based on reasoning output
workflow.add_conditional_edges(
    "reasoning",
    should_use_skill,
    {
        "skill_execution": "skill_execution",
        "response_formulation": "response_formulation"
    }
)
```

### Node Implementations
1. **Reasoning Node** (`services/agent_service/nodes/reasoning.py`)
   - Analyzes user input using LLM
   - Determines appropriate actions
   - Chooses skills or direct responses

2. **Skill Execution Node** (`services/agent_service/nodes/skill_execution.py`)
   - Executes selected skills via Skill Service
   - Handles skill parameters and validation
   - Processes skill results

3. **Response Formulation Node** (`services/agent_service/nodes/response_formulation.py`)
   - Creates final responses for users
   - Integrates skill results with context
   - Formats output appropriately

## Delegation System

The platform supports a supervisor-delegate pattern:

### Supervisor Agent
- Routes queries to specialized agents based on domain keywords
- Synthesizes responses from multiple agents
- Maintains conversation context across delegations

### Domain Registration
```bash
curl -X POST http://localhost:8001/agents \
  -d '{
    "config": {...},
    "domain": "finance", 
    "keywords": ["stocks", "market", "investment"]
  }'
```

### Current Domains
- **Research**: `research`, `analysis`, `sources`
- **Finance**: `stocks`, `market`, `investment`, `crypto`

## Redis Integration

Redis stores all platform state:

### Data Structures
- `agent:{agent_id}:config` - Agent configurations (Hash)
- `conversation:{conversation_id}` - Conversation data (Hash)  
- `agent:{agent_id}:memory` - Agent memory (Hash)
- `delegate:domain:{domain}` - Domain mappings (String)
- `skill:{skill_id}` - Skill definitions (Hash)

### Memory Management
- **Working Memory**: Current conversation context
- **Long-term Memory**: Key facts and conversation summaries
- **Skill Results**: Cached execution results

## Service Communication

All services communicate via HTTP APIs:

- **API Service** (8000): Main user interface
- **Agent Lifecycle** (8001): Agent management
- **Skill Service** (8002): Skill execution
- **Agent Service** (8003): Agent workflows
- **Redis** (6379): State storage

### Client Implementations
Each service has dedicated HTTP clients in `services/api/clients/` for type-safe inter-service communication.

## Development Workflow

### Setup
```bash
# Local development
python main.py

# Docker deployment  
docker-compose up --build

# Agent bootstrapping
./bootstrap.sh localhost
```

### Environment Variables
```
# Core LLM APIs
GEMINI_API_KEY=your_gemini_key
GROQ_API_KEY=your_groq_key
OPENROUTER_API_KEY=your_openrouter_key

# Skill APIs
SERPAPI_API_KEY=your_serpapi_key
ALPHAVANTAGE_API_KEY=your_alpha_vantage_key

# Infrastructure
REDIS_HOST=localhost
REDIS_PORT=6379
LOG_LEVEL=INFO

# Model Router (optional overrides)
MODEL_ROUTER_USE_REDIS=true
MODEL_ROUTER_LOG_LEVEL=info
```

## Deployment

### Local Development
Use `main.py` which orchestrates all services with process management and auto-restart capabilities.

### Docker Deployment
`docker-compose.yml` provides full multi-service deployment with:
- Service dependencies
- Volume mounting for development
- Redis persistence
- Redis Commander web UI (port 8081)

### Azure Cloud Deployment
`azure-deploy.sh` provides automated Azure Container Apps deployment with:
- Container registry integration
- Key Vault secret management
- Managed identity configuration
- Inter-service networking

## Testing

Comprehensive test suite in `tests/` covering:
- Unit tests for core functionality
- Integration tests for service communication
- End-to-end workflow testing
- Redis data integrity tests
- Agent delegation flows

## Agent Flow Tracking

The platform includes sophisticated execution tracking (`shared/models/agent_flow.py`):
- Flow visualization for debugging
- Performance monitoring
- Execution path analysis
- Multi-agent delegation tracking

## Development Standards

### Code Quality
- Complete type hints throughout
- Pydantic models for data validation
- Async/await for all I/O operations
- Structured error handling and logging

### Architecture Principles
- Service separation with clear APIs
- Redis-first state management
- LangGraph for complex workflows
- Docker-first deployment strategy

## Model Router System

The platform now includes a sophisticated Model Router that dynamically selects between multiple LLM providers based on agent roles, task types, and real-time RPM limits.

### Supported Models
- **Google Gemini 2.5 Flash**: High-speed model for general tasks
- **Groq LLaMA 3 70B**: High-capability model for complex reasoning
- **OpenRouter Fallback**: Universal fallback for any model

### Routing Matrix
- **Supervisor Agent**: Primary: Gemini Flash, Fallback: Groq LLaMA
- **Research Agent**: Primary: Gemini Flash, Fallback: Groq LLaMA  
- **Finance Agent**: Primary: Groq LLaMA, Fallback: Gemini Flash
- **Creative Agent**: Primary: Gemini Flash, Fallback: Groq LLaMA

### Key Features
- **RPM Tracking**: Redis-based sliding window rate limiting
- **Automatic Fallback**: Seamless switching when models hit limits
- **Direct API Support**: Bypasses OpenRouter when possible for lower latency
- **Real-time Monitoring**: Dashboard endpoints for routing statistics
- **Configuration Reload**: Runtime policy updates without restart

### Routing Dashboard
Access routing metrics at:
- `GET /routing/stats` - Overall routing statistics
- `GET /routing/health` - System health check
- `GET /routing/utilization/{model}` - Per-model utilization
- `POST /routing/reload` - Reload configuration

