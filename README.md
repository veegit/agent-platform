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
- Groq API key for LLM access (https://console.groq.com/)

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
   
5. Edit the `.env` file to add your SerpAPI and Groq API keys:
   ```
   SERPAPI_API_KEY=your_serpapi_key_here
   GROQ_API_KEY=your_groq_api_key_here
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
   
3. Edit the `.env` file to add your SerpAPI and Groq API keys

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
      "name": "Research Assistant",
      "description": "A helpful research assistant that can search the web and summarize information",
      "goals": ["Provide accurate information", "Help users with research tasks"],
      "constraints": ["Only use verified sources", "Respect user privacy"],
      "tone": "helpful and friendly",
      "system_prompt": "You are a research assistant. Help users find and summarize information from the web."
    },
    "llm": {
      "model_name": "llama3-70b-8192",
      "temperature": 0.7,
      "max_tokens": 2000
    },
    "skills": ["web-search", "summarize-text", "ask-follow-up"],
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

### Service Communication

Services communicate with each other via HTTP APIs, allowing for a distributed architecture. Each service can be deployed and scaled independently.