"""
Main application for the Skill Service.
"""

import logging
import os
from typing import List

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from shared.utils.redis_manager import RedisManager
from services.skill_service.registry import SkillRegistry
from services.skill_service.validator import SkillValidator
from services.skill_service.executor import SkillExecutor
from services.skill_service.router import router as skill_router

# Configure logging
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Skill Service",
    description="Service for registering and executing skills in the Agentic Platform",
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

# Initialize skill components
skill_registry = SkillRegistry(redis_manager)
skill_validator = SkillValidator()
skill_executor = SkillExecutor(skill_registry, skill_validator)


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize the service on startup."""
    logger.info("Starting Skill Service")
    
    # Connect to Redis
    await redis_manager.connect()
    
    # Initialize skill registry
    await skill_registry.initialize()
    
    # Discover and register built-in skills
    skills = await skill_executor.discover_skills()
    
    # Register discovered skills
    for skill in skills:
        try:
            # Check if skill already exists
            existing_skill = await skill_registry.get_skill(skill.skill_id)
            if existing_skill:
                logger.info(f"Skill {skill.name} ({skill.skill_id}) already registered")
                continue
            
            # Register skill
            await skill_registry.register_skill(skill)
            logger.info(f"Registered built-in skill: {skill.name} ({skill.skill_id})")
        except Exception as e:
            logger.error(f"Failed to register built-in skill {skill.name}: {e}")
    
    logger.info("Skill Service started successfully")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    logger.info("Shutting down Skill Service")
    await redis_manager.disconnect()


# Include skill router
app.include_router(skill_router)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    redis_healthy = await redis_manager.redis_client.ping()
    
    return {
        "status": "healthy" if redis_healthy else "unhealthy",
        "redis": "connected" if redis_healthy else "disconnected"
    }


# Run the application
if __name__ == "__main__":
    import uvicorn
    
    port = int(os.environ.get("SKILL_SERVICE_PORT", 8002))
    host = os.environ.get("SKILL_SERVICE_HOST", "0.0.0.0")
    
    uvicorn.run(
        "services.skill_service.main:app",
        host=host,
        port=port,
        reload=True
    )