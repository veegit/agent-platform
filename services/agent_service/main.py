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
from datetime import datetime # Ensure datetime is imported for Message model fallback

from shared.utils.redis_manager import RedisManager
from shared.utils.redis_agent_store import RedisAgentStore # Added import
from services.agent_service.models.config import AgentConfig, ReasoningModel, AgentPersona, MemoryConfig
from services.agent_service.models.state import Message, AgentState # Ensure Message is imported
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

# Redis Agent Store
redis_agent_store: Optional[RedisAgentStore] = None


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

    logger.info(f"Agent {agent_id} not in memory cache, attempting to load from Redis.")
    if not redis_agent_store:
        logger.error("RedisAgentStore not initialized. Cannot load agent from Redis.")
    else:
        try:
            loaded_agent_data = await redis_agent_store.get_agent(agent_id)
            logger.debug(f"Raw loaded_agent_data for {agent_id} from Redis: {loaded_agent_data}") # Log point 1

            if loaded_agent_data:
                logger.info(f"Agent {agent_id} found in Redis. Reconstructing agent instance.")
                
                config_data = loaded_agent_data.get('config')
                logger.debug(f"Extracted config_data for {agent_id}: {config_data}") # Log point 2

                if not config_data:
                    logger.error(f"Config data missing for agent {agent_id} in Redis. Data: {loaded_agent_data}")
                else:
                    persona_data = config_data.get('persona')
                    reasoning_model_str = config_data.get('reasoning_model', ReasoningModel.LLAMA3_70B.value) # Default if missing
                    memory_data = config_data.get('memory')
                    # Use skills from top level of loaded_agent_data as per previous logic, or from config if that was intended
                    skills_list = loaded_agent_data.get('skills', config_data.get('skills', [])) 
                    logger.debug(f"Skills list for {agent_id}: {skills_list}") # Log point 6
                    
                    default_skill_params = config_data.get('default_skill_params', {})
                    additional_config_data = config_data.get('additional_config', {})

                    if not persona_data:
                        logger.error(f"Persona data missing for agent {agent_id}. Using default placeholder.")
                        # Provide a default persona to allow agent creation
                        persona_data = {
                            "name": "Default Persona", 
                            "description": "Default description", 
                            "system_prompt": "You are a helpful assistant."
                        }
                    
                    logger.debug(f"Attempting to create AgentPersona for {agent_id} with data: {persona_data}") # Log point 3 (before)
                    try:
                        agent_persona = AgentPersona(**persona_data)
                        
                        logger.debug(f"Attempting to create ReasoningModel for {agent_id} from string: '{reasoning_model_str}'") # Log point 4 (before)
                        try:
                            reasoning_model_enum = ReasoningModel(reasoning_model_str)
                        except ValueError as e_reasoning:
                            logger.warning(f"Invalid reasoning model string '{reasoning_model_str}' for agent {agent_id}. Defaulting to LLAMA3_70B. Error: {e_reasoning}") # Log point 4 (except)
                            reasoning_model_enum = ReasoningModel.LLAMA3_70B
                        
                        agent_memory_config_instance = MemoryConfig() # Default instance
                        if memory_data:
                            logger.debug(f"Attempting to create MemoryConfig for {agent_id} with data: {memory_data}") # Log point 5 (before)
                            try:
                                agent_memory_config_instance = MemoryConfig(**memory_data)
                            except Exception as e_memory: # Catching generic Exception as Pydantic errors can vary
                                logger.error(f"Error creating MemoryConfig for agent {agent_id} with data {memory_data}: {e_memory}. Using default MemoryConfig.")
                        else:
                            logger.debug(f"No memory_data provided for {agent_id}. Using default MemoryConfig.")


                        reconstructed_agent_config = AgentConfig(
                            agent_id=agent_id, # Use the requested agent_id
                            persona=agent_persona,
                            reasoning_model=reasoning_model_enum,
                            skills=skills_list,
                            memory=agent_memory_config_instance,
                            default_skill_params=default_skill_params,
                            additional_config=additional_config_data
                        )
                        logger.info(f"Successfully reconstructed AgentConfig for {agent_id}: {reconstructed_agent_config.dict()}") # Log point 7

                        new_agent = Agent(
                            config=reconstructed_agent_config,
                            memory_manager=memory_manager,
                            skill_client=skill_client
                        )
                        await new_agent.initialize()
                        logger.info(f"Caching agent {agent_id} in agent_registry.") # Log point 9
                        agent_registry[agent_id] = new_agent
                        logger.info(f"Agent {agent_id} loaded from Redis and initialized successfully.")
                        return new_agent
                    except Exception as e: # Main reconstruction exception
                        # Log point 3 (except) - This covers AgentPersona creation if it fails within this broader try-except
                        if 'persona_data' in locals(): # Check if persona_data was defined
                             logger.error(f"Error during AgentPersona creation or subsequent model instantiation for {agent_id} with persona_data: {persona_data}. Full error: {e}")
                        # Log point 8 (comprehensive log)
                        logger.error(f"Error reconstructing agent {agent_id} from Redis data: {e}. Raw loaded_agent_data: {loaded_agent_data}")
            else:
                logger.info(f"Agent {agent_id} not found in Redis.")
        except Exception as e:
            logger.error(f"Failed to load agent {agent_id} from Redis (outer try-block): {e}")

    # Fallback logic if agent not loaded from Redis
    if "demo-agent" in agent_registry:
        logger.warning(f"Agent {agent_id} not loaded from Redis, using demo-agent as fallback.")
        return agent_registry["demo-agent"]
    
    logger.error(f"Agent {agent_id} not found in Redis, and demo-agent also not available.")
    raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found and demo-agent unavailable")


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize the service on startup."""
    logger.info("Starting Agent Service")
    
    # Connect to Redis
    await redis_manager.connect()
    
    # Initialize memory manager
    await memory_manager.initialize()

    # Initialize RedisAgentStore
    global redis_agent_store
    redis_agent_store = RedisAgentStore(redis_client=redis_manager.redis_client)
    logger.info("RedisAgentStore initialized.")
    
    # Create a demo agent
    demo_agent_id = "demo-agent"
    
    # Get available skills from skill service
    try:
        available_skills = await skill_client.get_available_skills()
        skill_ids = [skill["skill_id"] for skill in available_skills]
        logger.info(f"Found {len(skill_ids)} available skills: {skill_ids}")
    except Exception as e:
        logger.error(f"Failed to get available skills: {e}")
        skill_ids = ["web-search", "summarize-text", "ask-follow-up"]
    
    # Create demo agent config
    demo_config = AgentConfig(
        agent_id=demo_agent_id,
        persona=AgentPersona(
            name="Research Assistant",
            description="A helpful research assistant that can search the web and summarize information.",
            goals=["Provide accurate information", "Assist with research tasks"],
            constraints=["Do not make up facts", "Cite sources when possible"],
            tone="professional and helpful",
            system_prompt="You are a research assistant that helps users find and understand information. Always strive to provide factual, accurate responses and assist the user with their research needs."
        ),
        reasoning_model=ReasoningModel.LLAMA3_70B,
        skills=skill_ids,
        memory=MemoryConfig(
            max_messages=50,
            summarize_after=20,
            long_term_memory_enabled=True,
            key_fact_extraction_enabled=True
        )
    )
    
    # Create demo agent
    demo_agent = Agent(
        config=demo_config,
        memory_manager=memory_manager,
        skill_client=skill_client
    )
    
    # Initialize agent
    await demo_agent.initialize()
    
    # Add to registry
    agent_registry[demo_agent_id] = demo_agent
    
    logger.info(f"Created demo agent {demo_agent_id}")
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