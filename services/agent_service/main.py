"""
Main application for the Agent Service.
"""

import logging
import os
import uuid
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, HTTPException, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from shared.utils.redis_manager import RedisManager
from services.agent_service.models.config import AgentConfig, ReasoningModel, AgentPersona, MemoryConfig
from services.agent_service.models.state import Message, AgentState
from services.agent_service.memory import MemoryManager
from services.agent_service.skill_client import SkillServiceClient
from services.agent_service.agent import Agent

# Configure logging
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Agent Service",
    description="Service for running agent workflows in the Agentic Platform",
    version="0.1.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development; restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Redis manager
redis_manager = RedisManager(
    host=os.environ.get("REDIS_HOST", "localhost"),
    port=int(os.environ.get("REDIS_PORT", 6379)),
    db=int(os.environ.get("REDIS_DB", 0)),
    password=os.environ.get("REDIS_PASSWORD")
)

# Initialize memory manager
memory_manager = MemoryManager(redis_manager)

# Initialize skill client
skill_client = SkillServiceClient(
    base_url=os.environ.get("SKILL_SERVICE_URL", "http://localhost:8002")
)

# Agent registry (in-memory for now, would move to Redis for production)
agent_registry: Dict[str, Agent] = {}


# Models for API
class MessageRequest(BaseModel):
    """Model for a message request."""
    
    user_id: str = Field(..., description="ID of the user sending the message")
    message: str = Field(..., description="Message content")
    conversation_id: Optional[str] = Field(None, description="ID of the conversation")


class MessageResponse(BaseModel):
    """Model for a message response."""
    
    agent_id: str = Field(..., description="ID of the agent")
    conversation_id: str = Field(..., description="ID of the conversation")
    message: Message = Field(..., description="The agent's response message")


# Dependency to get an agent by ID
async def _load_delegations() -> Dict[str, Dict[str, Agent]]:
    """Load delegation mappings from Redis and return agent objects."""
    mappings = await redis_manager.delegation_store.get_all_domains()
    delegations: Dict[str, Dict[str, Agent]] = {}

    for domain, data in mappings.items():
        delegate_id = data.get("agent_id")
        if not delegate_id:
            continue

        if delegate_id not in agent_registry:
            stored = await redis_manager.agent_store.get_agent(delegate_id)
            if stored:
                conf = AgentConfig(**stored["config"])
                agent = Agent(conf, memory_manager=memory_manager, skill_client=skill_client)
                await agent.initialize()
                agent_registry[delegate_id] = agent

        if delegate_id in agent_registry:
            delegations[domain] = {"agent": agent_registry[delegate_id]}

    return delegations


async def get_agent(agent_id: str) -> Agent:
    """Get an agent by ID.
    
    Args:
        agent_id: The ID of the agent.
        
    Returns:
        Agent: The agent instance.
        
    Raises:
        HTTPException: If the agent is not found.
    """
    if agent_id in agent_registry:
        return agent_registry[agent_id]
    
    agent_data = await redis_manager.agent_store.get_agent(agent_id)

    if agent_data:
        config = AgentConfig(**agent_data["config"])
        delegations = None
        if config.is_supervisor:
            delegations = await _load_delegations()
        loaded_agent = Agent(
            config=config,
            memory_manager=memory_manager,
            skill_client=skill_client,
            delegations=delegations,
        )
        await loaded_agent.initialize()
        agent_registry[agent_id] = loaded_agent
        logger.info(f"Loaded agent {agent_id} from Redis into registry")
        return loaded_agent

    
    # Use the default agent as a fallback if available
    if "default-agent" in agent_registry:
        logger.warning(
            f"Agent {agent_id} not found, using default-agent as fallback"
        )
        return agent_registry["default-agent"]
    
    # If no agent found and no demo agent, return 404
    raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize the service on startup."""
    logger.info("Starting Agent Service")
    
    # Connect to Redis
    await redis_manager.connect()
    
    # Initialize memory manager
    await memory_manager.initialize()
    
    # Get available skills from the skill service
    try:
        available_skills = await skill_client.get_available_skills()
        skill_ids = [skill["skill_id"] for skill in available_skills]
        logger.info(f"Found {len(skill_ids)} available skills: {skill_ids}")
    except Exception as e:
        logger.error(f"Failed to get available skills: {e}")
        skill_ids = ["web-search", "summarize-text", "ask-follow-up", "finance"]

    existing_agents = await redis_manager.agent_store.list_agents()

    if not existing_agents:
        # ----- Create Finance Agent -----
        finance_config = AgentConfig(
            agent_id="finance-agent",
            persona=AgentPersona(
                name="Finance Agent",
                description="Provides stock information",
                goals=["Answer finance questions"],
                constraints=["Use the finance skill"],
                tone="neutral",
                system_prompt="You are a finance assistant that can retrieve stock prices.",
            ),
            reasoning_model=ReasoningModel.LLAMA3_70B,
            skills=["finance"],
            memory=MemoryConfig(),
            is_supervisor=False,
        )

        finance_agent = Agent(finance_config, memory_manager=memory_manager, skill_client=skill_client)
        await finance_agent.initialize()
        agent_registry["finance-agent"] = finance_agent
        await redis_manager.delegation_store.register_domain("finance", "finance-agent", ["stock", "share", "ticker"], ["finance"])

        # ----- Create Default General Agent -----
        default_agent_id = "default-agent"
        general_skill_ids = [s for s in skill_ids if s != "finance"]

        default_config = AgentConfig(
            agent_id=default_agent_id,
            persona=AgentPersona(
                name="General Agent",
                description="Handles general questions",
                goals=["Assist with everyday queries"],
                constraints=["Be concise"],
                tone="helpful",
                system_prompt="You are a helpful general assistant.",
            ),
            reasoning_model=ReasoningModel.LLAMA3_70B,
            skills=general_skill_ids,
            memory=MemoryConfig(),
            is_supervisor=False,
        )

        general_agent = Agent(default_config, memory_manager=memory_manager, skill_client=skill_client)
        await general_agent.initialize()
        agent_registry[default_agent_id] = general_agent
        await redis_manager.delegation_store.register_domain("general", "default-agent", ["general"], general_skill_ids)

        # ----- Create Supervisor Agent -----
        supervisor_config = AgentConfig(
            agent_id="supervisor-agent",
            persona=AgentPersona(
                name="Supervisor Agent",
                description="Coordinates specialized agents",
                goals=["Delegate queries to the right agent"],
                constraints=["No direct skills"],
                tone="helpful",
                system_prompt="You coordinate other agents to answer user questions.",
            ),
            reasoning_model=ReasoningModel.LLAMA3_70B,
            skills=[],
            memory=MemoryConfig(),
            is_supervisor=True,
        )

        supervisor_agent = Agent(
            supervisor_config,
            memory_manager=memory_manager,
            skill_client=skill_client,
            delegations={
                "finance": {"agent": finance_agent},
                "general": {"agent": general_agent},
            },
        )
        await supervisor_agent.initialize()
        agent_registry["supervisor-agent"] = supervisor_agent

        logger.info("Created supervisor, finance, and general agents")
    else:
        logger.info(f"Existing agents found: {existing_agents}. Loading agents")
        for agent_id in existing_agents:
            data = await redis_manager.agent_store.get_agent(agent_id)
            if not data:
                continue
            config = AgentConfig(**data["config"])
            delegations = None
            if config.is_supervisor:
                delegations = await _load_delegations()
            agent = Agent(
                config,
                memory_manager=memory_manager,
                skill_client=skill_client,
                delegations=delegations,
            )
            await agent.initialize()
            agent_registry[agent_id] = agent

        logger.info("Loaded existing agents into registry")

    logger.info("Agent Service started successfully")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    logger.info("Shutting down Agent Service")
    await redis_manager.disconnect()


# Agent routes
@app.post("/agents/{agent_id}/chat", response_model=MessageResponse)
async def send_message(
    agent_id: str,
    request: MessageRequest,
    agent: Agent = Depends(get_agent)
):
    """Send a message to an agent and get a response.
    
    Args:
        agent_id: The ID of the agent to send the message to.
        request: The message request.
        agent: The agent instance.
        
    Returns:
        MessageResponse: The agent's response.
    """
    try:
        response = await agent.process_message(
            user_message=request.message,
            user_id=request.user_id,
            conversation_id=request.conversation_id
        )
        
        return MessageResponse(
            agent_id=agent_id,
            conversation_id=response.state.conversation_id,
            message=response.message
        )
    
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        # Return a fallback response instead of raising an exception
        return MessageResponse(
            agent_id=agent_id,
            conversation_id=request.conversation_id or str(uuid.uuid4()),
            message=Message(
                id=str(uuid.uuid4()),
                role="agent",
                content="I'm sorry, I encountered an error while processing your message. Please try again later.",
                timestamp=datetime.now()
            )
        )


@app.get("/agents/{agent_id}/conversations/{conversation_id}/history", response_model=List[Message])
async def get_conversation_history(
    agent_id: str,
    conversation_id: str,
    agent: Agent = Depends(get_agent)
):
    """Get the conversation history.
    
    Args:
        agent_id: The ID of the agent.
        conversation_id: The ID of the conversation.
        agent: The agent instance.
        
    Returns:
        List[Message]: The conversation history.
    """
    try:
        return await agent.get_conversation_history(conversation_id)
    
    except Exception as e:
        logger.error(f"Error getting conversation history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get conversation history: {str(e)}")


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    redis_healthy = await redis_manager.redis_client.ping()
    
    # Check if we can connect to the skill service
    skill_service_healthy = False
    try:
        skills = await skill_client.get_available_skills()
        skill_service_healthy = len(skills) > 0
    except Exception:
        skill_service_healthy = False
    
    return {
        "status": "healthy" if redis_healthy and skill_service_healthy else "unhealthy",
        "redis": "connected" if redis_healthy else "disconnected",
        "skill_service": "connected" if skill_service_healthy else "disconnected"
    }


# Run the application
if __name__ == "__main__":
    import uvicorn
    
    port = int(os.environ.get("AGENT_SERVICE_PORT", 8003))
    host = os.environ.get("AGENT_SERVICE_HOST", "0.0.0.0")
    
    uvicorn.run(
        "services.agent_service.main:app",
        host=host,
        port=port,
        reload=True
    )
