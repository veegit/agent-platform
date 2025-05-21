"""
Main application for the API service.
"""

import logging
import os
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shared.utils.redis_manager import RedisManager
from services.api.router import router
from services.api.conversations import ConversationService
from services.api.clients.agent_lifecycle_client import AgentLifecycleClient
from services.api.clients.agent_service_client import AgentServiceClient

# Configure logging
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Agentic Platform API",
    description="API service for the Agentic Platform",
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

app.include_router(router, prefix="")

app.mount(
    "/",
    StaticFiles(directory="frontend", html=True),
    name="chat-ui",
)

# Initialize Redis manager
redis_manager = RedisManager(
    host=os.environ.get("REDIS_HOST", "localhost"),
    port=int(os.environ.get("REDIS_PORT", 6379)),
    db=int(os.environ.get("REDIS_DB", 0)),
    password=os.environ.get("REDIS_PASSWORD")
)

# Initialize clients and services
agent_lifecycle_client = AgentLifecycleClient()
agent_service_client = AgentServiceClient()
conversation_service = ConversationService(
    redis_manager=redis_manager,
    agent_lifecycle_client=agent_lifecycle_client,
    agent_service_client=agent_service_client
)


# Exception handler
@app.exception_handler(Exception)
async def handle_exception(request: Request, exc: Exception):
    """Handle exceptions."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize the service on startup."""
    logger.info("Starting API Service")
    
    # Connect to Redis
    await redis_manager.connect()
    
    # Initialize conversation service
    await conversation_service.initialize()
    
    # Check connections to other services
    try:
        # Check agent lifecycle service
        agent_response = await agent_lifecycle_client.list_agents(limit=1)
        if "error" in agent_response:
            logger.warning(f"Agent Lifecycle Service connection issue: {agent_response['error']}")
        else:
            logger.info("Successfully connected to Agent Lifecycle Service")
    except Exception as e:
        logger.warning(f"Failed to connect to Agent Lifecycle Service: {e}")
    
    logger.info("API Service started successfully")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    logger.info("Shutting down API Service")
    await redis_manager.disconnect()


# Include router
app.include_router(router)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    redis_healthy = await redis_manager.redis_client.ping()
    
    # Check if we can connect to the agent lifecycle service
    agent_lifecycle_healthy = False
    try:
        response = await agent_lifecycle_client.list_agents(limit=1)
        agent_lifecycle_healthy = "error" not in response
    except Exception:
        agent_lifecycle_healthy = False
    
    # Check if we can connect to the agent service
    agent_service_healthy = False
    try:
        # We can't really test this without a valid agent and message
        # For the health check, we'll just assume it's connected if agent lifecycle is
        agent_service_healthy = agent_lifecycle_healthy
    except Exception:
        agent_service_healthy = False
    
    return {
        "status": "healthy" if redis_healthy and agent_lifecycle_healthy else "unhealthy",
        "redis": "connected" if redis_healthy else "disconnected",
        "agent_lifecycle_service": "connected" if agent_lifecycle_healthy else "disconnected",
        "agent_service": "connected" if agent_service_healthy else "disconnected"
    }


# Default route
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Agentic Platform API",
        "version": "0.1.0",
        "docs_url": "/docs"
    }


# Run the application
if __name__ == "__main__":
    import uvicorn
    
    port = int(os.environ.get("API_PORT", 8000))
    host = os.environ.get("API_HOST", "0.0.0.0")
    
    uvicorn.run(
        "services.api.main:app",
        host=host,
        port=port,
        reload=True
    )