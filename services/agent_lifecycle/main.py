"""
Main application for the Agent Lifecycle Service.
"""

import logging
import os
from typing import Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from shared.utils.redis_manager import RedisManager
from services.agent_lifecycle.router import router as agent_router
from services.agent_lifecycle.repository import AgentRepository

# Configure logging
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Agent Lifecycle Service",
    description="Service for managing agent lifecycle in the Agentic Platform",
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

# Initialize repository
repository = AgentRepository(redis_manager)


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize the service on startup."""
    logger.info("Starting Agent Lifecycle Service")
    
    # Connect to Redis
    await redis_manager.connect()
    
    # Initialize repository
    await repository.initialize()
    
    logger.info("Agent Lifecycle Service started successfully")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    logger.info("Shutting down Agent Lifecycle Service")
    await redis_manager.disconnect()


# Include agent router
app.include_router(agent_router)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    redis_healthy = await redis_manager.redis_client.ping()
    
    return {
        "status": "healthy" if redis_healthy else "unhealthy",
        "redis": "connected" if redis_healthy else "disconnected"
    }


# Default route
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Agent Lifecycle Service",
        "version": "0.1.0",
        "docs_url": "/docs"
    }


# Run the application
if __name__ == "__main__":
    import uvicorn
    
    port = int(os.environ.get("AGENT_LIFECYCLE_PORT", 8001))
    host = os.environ.get("AGENT_LIFECYCLE_HOST", "0.0.0.0")
    
    uvicorn.run(
        "services.agent_lifecycle.main:app",
        host=host,
        port=port,
        reload=True
    )