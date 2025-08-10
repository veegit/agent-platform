# Agentic Platform

A platform for creating, managing and interacting with AI agents powered by LangGraph, FastAPI, and Redis.

## Architecture

The platform consists of four main components:

1. **Agent Lifecycle Service**: Manages agent creation, configuration, and status
2. **Skill Service**: Provides a registry of skills that agents can use
3. **Agent Service**: Runs agent workflows using LangGraph
4. **API Service**: Provides user-facing endpoints for interacting with agents

All services use Redis for state management and inter-service communication.

## Setup

### Prerequisites
- Python 3.11+
- Redis (for local development)
- SerpAPI key for web search skill (https://serpapi.com/)
- Gemini API key for LLM access (https://aistudio.google.com/app/apikey)
- Alpha Vantage API key for finance skill (https://www.alphavantage.co/)

### Local Installation
1. Clone the repository
   ```
   git clone https://github.com/yourusername/agent-platform.git
   cd agent-platform
   ```

2. Set up a virtual environment (recommended)
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   pip install langgraph==0.0.15
   ```

4. Copy environment file and add your API keys:
   ```
   cp .env.example .env
   ```
   
5. Edit the `.env` file to add your API keys:
   ```
   SERPAPI_API_KEY=your_serpapi_key_here
   GEMINI_API_KEY=your_gemini_api_key_here
   ALPHAVANTAGE_API_KEY=your_alpha_vantage_key_here
   ```

### Docker Installation
1. Clone the repository
   ```
   git clone https://github.com/yourusername/agent-platform.git
   cd agent-platform
   ```

2. Copy environment file and add your API keys:
   ```
   cp .env.example .env
   ```
   
3. Edit the `.env` file to add your API keys

4. Build and run the Docker containers:
   ```
   docker-compose up --build
   ```

## Running the Platform

### Using Python (Local Development)
Start all services together with the main script:
```
python main.py
```

This will start all services, including an embedded Redis server.

#### Options:
- Start without Redis (if you have Redis running separately)
  ```
  python main.py --exclude redis
  ```
- Start specific services only
  ```
  python main.py --exclude redis api agent_service
  ```

### Using Docker (Recommended)
```
docker-compose up --build
```

If you encounter any issues with the LangGraph installation in Docker, try rebuilding with:
```
docker-compose build --no-cache
docker-compose up
```

#### For development with hot-reloading:
```
docker-compose up --build
```
This will mount the local directory in the container and enable auto-reloading when files change.

## API Endpoints

The platform provides a RESTful API for managing agents, conversations, and skills.

### Agent Management
- `POST /agents` - Create a new agent
- `GET /agents` - List all agents
- `GET /agents/{agent_id}` - Get agent details
- `PUT /agents/{agent_id}/status` - Update agent status (activate/deactivate agent)
- `PUT /agents/{agent_id}/config` - Update agent configuration
- `DELETE /agents/{agent_id}` - Delete an agent

### Conversations
- `POST /conversations` - Start a new conversation
- `GET /conversations` - List conversations (filter by user or agent)
- `GET /conversations/{conversation_id}` - Get conversation details
- `POST /conversations/{conversation_id}/messages` - Send a message to an agent
- `GET /conversations/{conversation_id}/messages` - Get message history

### Skills
- `GET /skills` - List available skills
- `POST /skills/execute` - Execute a skill directly
- `GET /skills/{skill_id}` - Get skill details

## Example Usage

### Create an Agent

```bash
curl -X POST http://localhost:8001/agents -H "Content-Type: application/json" -d '{
  "config": {
    "agent_id": "",
    "persona": {
      "name": "Supervisor Agent",
      "description": "Coordinates specialized agents to assist with complex queries",
      "goals": ["Provide accurate information", "Delegate to domain experts when necessary"],
      "constraints": ["Only use verified sources", "Respect user privacy"],
      "tone": "helpful and friendly",
      "system_prompt": "You manage a team of domain experts. Coordinate with them only when necessary and avoid mentioning them unless relevant."
    },
    "llm": {
      "model_name": "gemini-2.5-flash",
      "temperature": 0.7,
      "max_tokens": 2000
    },
    "skills": [],
    "memory": {
      "max_messages": 50,
      "summarize_after": 20,
      "long_term_memory_enabled": true,
      "key_fact_extraction_enabled": true
    }
  }
}'
```

### Activate an Agent

```bash
curl -X PUT http://localhost:8001/agents/YOUR_AGENT_ID/status -H "Content-Type: application/json" -d '{
  "status": "active"
}'
```

### Start a Conversation

```bash
curl -X POST http://localhost:8000/conversations -H "Content-Type: application/json" -d '{
  "agent_id": "YOUR_AGENT_ID",
  "user_id": "user123",
  "initial_message": "Tell me about artificial intelligence"
}'
```

### Send a Message

```bash
curl -X POST http://localhost:8000/conversations/YOUR_CONVERSATION_ID/messages -H "Content-Type: application/json" -d '{
  "content": "What are the latest developments in machine learning?",
  "user_id": "user123"
}'
```

### List Available Skills

```bash
curl -X GET http://localhost:8002/skills
```

### Execute a Skill Directly

```bash
curl -X POST http://localhost:8002/skills/execute -H "Content-Type: application/json" -d '{
  "skill_id": "web-search",
  "parameters": {
    "query": "latest AI developments",
    "num_results": 5
  }
}'
```

## Built-in Skills

The platform comes with several built-in skills:

1. **Web Search** (`web-search`): Search the web using SerpAPI
   - Parameters: `query`, `num_results`, `include_images`, `search_type`

2. **Summarize Text** (`summarize-text`): Summarize long text content
   - Parameters: `text`, `max_length`, `format`

3. **Ask Follow-up Questions** (`ask-follow-up`): Generate follow-up questions based on context
   - Parameters: `context`, `num_questions`
4. **Finance Skill** (`finance`): Get the latest stock price using Alpha Vantage
   - Parameters: `symbol`

## Agent Management & Delegate System

### Bootstrap Script

The platform includes a bootstrap script that can recreate your entire agent setup from scratch. This is particularly useful when you need to reset your Redis volume or set up a new environment.

**Usage:**
```bash
./bootstrap.sh <hostname>
```

**Examples:**
```bash
# For local development
./bootstrap.sh localhost

# For remote deployment
./bootstrap.sh 192.168.1.100
```

The bootstrap script will:
1. Create all agents (Supervisor, Research, Finance) with their configurations
2. Set up delegate domain mappings automatically
3. Activate all agents
4. Verify the setup

### Delegate Management

The platform uses a sophisticated delegate system where the Supervisor Agent routes queries to specialized agents based on domain expertise.

#### Current Delegate Domains:
- **Research Domain**: Handled by Research Agent
  - Keywords: `research`, `analysis`, `sources`
  - Skills: `ask-follow-up`, `summarize-text`, `web-search`

- **Finance Domain**: Handled by Finance Agent  
  - Keywords: `stocks`, `market`, `investment`
  - Skills: `finance`

#### Managing Delegates via API

**Create Agent with Delegate Domain:**
```bash
curl -X POST http://localhost:8001/agents \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "agent_id": "healthcare-agent",
      "persona": {
        "name": "Healthcare Agent",
        "description": "Provides medical information and health advice",
        "goals": ["Provide accurate health information"],
        "constraints": ["No diagnostic advice"],
        "tone": "caring and professional",
        "system_prompt": "You are a healthcare information specialist."
      },
      "llm": {
        "model_name": "gemini-2.5-flash",
        "temperature": 0.7,
        "max_tokens": 2000,
        "provider": "gemini"
      },
      "skills": ["web-search"],
      "is_supervisor": false
    },
    "domain": "healthcare",
    "keywords": ["medical", "health", "doctor", "medicine"]
  }'
```

**Update Agent Delegate Configuration:**
```bash
curl -X PUT http://localhost:8001/agents/finance-agent/config \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "agent_id": "finance-agent",
      "persona": {
        "name": "Finance Agent",
        "description": "Enhanced financial analysis agent",
        "goals": ["Provide comprehensive market analysis"],
        "constraints": ["No investment advice"],
        "tone": "professional",
        "system_prompt": "You specialize in financial data and market analysis."
      },
      "llm": {
        "model_name": "gemini-2.5-flash",
        "temperature": 0.7,
        "max_tokens": 2000,
        "provider": "gemini"
      },
      "skills": ["finance", "web-search"],
      "is_supervisor": false
    },
    "domain": "finance",
    "keywords": ["stocks", "market", "investment", "crypto", "trading", "portfolio"]
  }'
```

**List All Agents with Delegate Information:**
```bash
curl -X GET http://localhost:8001/agents | jq '.agents[] | {agent_id, domain, keywords}'
```

#### How Delegation Works

1. **User Query**: User sends a message to the platform
2. **Supervisor Analysis**: Supervisor Agent analyzes the query using LLM reasoning
3. **Domain Matching**: System matches query intent to delegate domains using keywords
4. **Agent Routing**: Query is routed to the appropriate specialized agent
5. **Response Synthesis**: Supervisor may synthesize responses from multiple agents
6. **Fallback**: If no specialized agent matches, falls back to general agent

#### Verifying Delegate Setup

Check delegate mappings in Redis:
```bash
docker exec -it agent-platform-redis-1 redis-cli keys "delegate:*"
docker exec -it agent-platform-redis-1 redis-cli get "delegate:domain:finance"
```

## Service Ports

The platform runs several services, each on its own port:

- **API Service**: http://localhost:8000 - Main API for client applications
- **Agent Lifecycle Service**: http://localhost:8001 - Manages agent configuration
- **Skill Service**: http://localhost:8002 - Manages skills and skill execution
- **Agent Service**: http://localhost:8003 - Runs agent workflows
- **Redis Commander (via Docker)**: http://localhost:8081 - Web UI for Redis

Interactive API documentation is available at `/docs` for each service (e.g., http://localhost:8000/docs)

## Architecture Details

### LangGraph Implementation

The agent's workflow is implemented using LangGraph, a framework for creating structured agent workflows. The workflow consists of three main nodes:

1. **Reasoning**: Determines what action to take based on user input
2. **Skill Execution**: Executes skills based on the reasoning
3. **Response Formulation**: Creates the final response to the user

### Redis Integration

Redis is used for:
- Storing agent configurations
- Managing conversation history
- Tracking agent state
- Storing skill registrations and results
- Maintaining a domain -> agent delegation registry for supervisor agents

### Service Communication

Services communicate with each other via HTTP APIs, allowing for a distributed architecture. Each service can be deployed and scaled independently.

## Deployment
### Continuous Deployment

A GitHub Actions workflow is set up to automatically deploy to Azure whenever code is pushed to the main branch. The workflow is defined in `.github/workflows/azure-deploy.yml`.

To set up continuous deployment:

1. Add the following secrets to your GitHub repository:
   - `AZURE_CREDENTIALS`: Azure service principal credentials (JSON format)
   - `ACR_USERNAME`: Azure Container Registry username
   - `ACR_PASSWORD`: Azure Container Registry password

2. Push to the main branch to trigger the automatic deployment.

You can also manually trigger the workflow from the "Actions" tab in your GitHub repository.

The workflow will:
1. Build Docker images for all four services
2. Push the images to Azure Container Registry
3. Update all Container Apps with the new images
4. Configure environment variables to ensure proper inter-service communication

### Manual Azure Deployment

The platform can be deployed to Azure Container Apps for a scalable, managed environment.

#### Prerequisites
- Azure CLI installed and logged in
- An Azure subscription
- Access to Azure Container Registry (ACR)
- Azure Key Vault with the following secrets:
  - `REDIS-PASSWORD`: Password for Azure Cache for Redis
  - `SERP-API-KEY`: Your SerpAPI key
  - `GROQ-API-KEY`: Your Groq API key

#### Initial Deployment

For first-time deployment, use the `azure-deploy.sh` script with the `--initial` flag:

```bash
# Make the script executable if needed
chmod +x azure-deploy.sh

# Run the initial deployment
./azure-deploy.sh --initial
```

This will:
1. Build Docker images for all four services
2. Push the images to Azure Container Registry
3. Create a managed identity for accessing Key Vault secrets
4. Deploy all services to Azure Container Apps
5. Configure inter-service communication

#### Redeploying After Changes

For subsequent deployments after code changes:

```bash
./azure-deploy.sh
```

This will rebuild and update all services without recreating resources like managed identities.

#### Customizing the Deployment

You can customize the deployment by using the following options:

```bash
./azure-deploy.sh [--resource-group RESOURCE_GROUP] [--acr ACR_NAME] \
                   [--keyvault KEYVAULT_NAME] [--environment ENVIRONMENT_NAME] \
                   [--identity IDENTITY_NAME] [--initial]
```

All parameters are optional and will use defaults if not specified:
- `--resource-group`: Azure resource group (default: "agent-platform-rg")
- `--acr`: Azure Container Registry name (default: "agentplatformacr")
- `--keyvault`: Key Vault name (default: "agent-platform-kv")
- `--environment`: Container Apps environment (default: "agent-platform-env")
- `--identity`: Managed identity name (default: "agent-platform-identity")
- `--initial`: Flag for initial deployment (creates resources)
