"""
Routing Dashboard API endpoints for monitoring model routing decisions.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from shared.utils.model_router import get_model_router

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/routing", tags=["routing"])


class RoutingStatsResponse(BaseModel):
    """Response model for routing statistics."""
    models: Dict[str, Any]
    timestamp: datetime
    total_requests: int
    fallback_rate: float


class ModelUtilizationResponse(BaseModel):
    """Response model for model utilization."""
    model_id: str
    current_rpm: int
    rpm_limit: int
    utilization_percent: float
    cost_per_1k_tokens: float
    avg_latency_ms: int


class RoutingHealthResponse(BaseModel):
    """Response model for routing health check."""
    status: str
    healthy_models: List[str]
    unhealthy_models: List[str]
    high_utilization_models: List[str]
    total_models: int


@router.get("/stats", response_model=RoutingStatsResponse)
async def get_routing_stats():
    """
    Get current routing statistics for all models.
    
    Returns:
        RoutingStatsResponse: Current routing statistics
    """
    try:
        model_router = get_model_router()
        stats = await model_router.get_routing_stats()
        
        # Calculate overall metrics
        total_requests = sum(model_stats["current_rpm"] for model_stats in stats.values())
        
        # Calculate fallback rate (simplified - would need more sophisticated tracking in production)
        fallback_requests = 0  # This would need to be tracked by the router
        fallback_rate = fallback_requests / total_requests if total_requests > 0 else 0.0
        
        return RoutingStatsResponse(
            models=stats,
            timestamp=datetime.utcnow(),
            total_requests=total_requests,
            fallback_rate=fallback_rate
        )
        
    except Exception as e:
        logger.error(f"Error getting routing stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get routing statistics")


@router.get("/utilization/{model_name}", response_model=ModelUtilizationResponse)
async def get_model_utilization(model_name: str):
    """
    Get utilization statistics for a specific model.
    
    Args:
        model_name: Name of the model (e.g., 'gemini_flash', 'groq_llama_70b')
        
    Returns:
        ModelUtilizationResponse: Model utilization statistics
    """
    try:
        model_router = get_model_router()
        stats = await model_router.get_routing_stats()
        
        if model_name not in stats:
            raise HTTPException(status_code=404, detail=f"Model {model_name} not found")
        
        model_stats = stats[model_name]
        
        return ModelUtilizationResponse(
            model_id=model_stats["id"],
            current_rpm=model_stats["current_rpm"],
            rpm_limit=model_stats["rpm_limit"],
            utilization_percent=model_stats["utilization_percent"],
            cost_per_1k_tokens=model_stats["cost_per_1k_tokens"],
            avg_latency_ms=model_stats["avg_latency_ms"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting model utilization for {model_name}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get model utilization")


@router.get("/health", response_model=RoutingHealthResponse)
async def get_routing_health(
    high_utilization_threshold: float = Query(0.8, description="Threshold for high utilization (0.0-1.0)")
):
    """
    Get health status of the routing system.
    
    Args:
        high_utilization_threshold: Threshold for considering a model as high utilization
        
    Returns:
        RoutingHealthResponse: Health status of all models
    """
    try:
        model_router = get_model_router()
        stats = await model_router.get_routing_stats()
        
        healthy_models = []
        unhealthy_models = []
        high_utilization_models = []
        
        for model_name, model_stats in stats.items():
            utilization = model_stats["utilization_percent"] / 100.0
            
            if utilization >= 1.0:
                # Model is at 100% capacity
                unhealthy_models.append(model_name)
            elif utilization >= high_utilization_threshold:
                # Model is at high utilization but not unhealthy
                high_utilization_models.append(model_name)
                healthy_models.append(model_name)
            else:
                healthy_models.append(model_name)
        
        # Determine overall status
        if len(unhealthy_models) == len(stats):
            status = "critical"
        elif len(unhealthy_models) > 0:
            status = "degraded"
        elif len(high_utilization_models) > 0:
            status = "warning"
        else:
            status = "healthy"
        
        return RoutingHealthResponse(
            status=status,
            healthy_models=healthy_models,
            unhealthy_models=unhealthy_models,
            high_utilization_models=high_utilization_models,
            total_models=len(stats)
        )
        
    except Exception as e:
        logger.error(f"Error getting routing health: {e}")
        raise HTTPException(status_code=500, detail="Failed to get routing health")


@router.post("/reload")
async def reload_routing_config():
    """
    Reload the routing configuration from file.
    
    Returns:
        Dict: Confirmation message
    """
    try:
        model_router = get_model_router()
        model_router.reload_config()
        
        logger.info("Routing configuration reloaded successfully")
        return {"message": "Routing configuration reloaded successfully"}
        
    except Exception as e:
        logger.error(f"Error reloading routing config: {e}")
        raise HTTPException(status_code=500, detail="Failed to reload routing configuration")


@router.get("/policies")
async def get_routing_policies():
    """
    Get current routing policies for all agent roles.
    
    Returns:
        Dict: Current routing policies
    """
    try:
        model_router = get_model_router()
        
        # Convert routing policies to a serializable format
        policies = {}
        for role, policy in model_router.routing_policies.items():
            policies[role] = {
                "primary": policy.primary,
                "fallback": policy.fallback
            }
        
        return {
            "policies": policies,
            "models": {
                name: {
                    "id": config.id,
                    "rpm_limit": config.rpm_limit,
                    "cost_per_1k_tokens_usd": config.cost_per_1k_tokens_usd,
                    "latency_ms_avg": config.latency_ms_avg
                }
                for name, config in model_router.models.items()
            },
            "fallback_behavior": model_router.fallback_behavior
        }
        
    except Exception as e:
        logger.error(f"Error getting routing policies: {e}")
        raise HTTPException(status_code=500, detail="Failed to get routing policies")


@router.get("/models")
async def get_available_models():
    """
    Get list of all available models and their configurations.
    
    Returns:
        Dict: Available models and their configurations
    """
    try:
        model_router = get_model_router()
        
        models = {}
        for name, config in model_router.models.items():
            models[name] = {
                "id": config.id,
                "rpm_limit": config.rpm_limit,
                "cost_per_1k_tokens_usd": config.cost_per_1k_tokens_usd,
                "latency_ms_avg": config.latency_ms_avg
            }
        
        return {"models": models}
        
    except Exception as e:
        logger.error(f"Error getting available models: {e}")
        raise HTTPException(status_code=500, detail="Failed to get available models")


# Include the router in the main API router
def get_routing_dashboard_router() -> APIRouter:
    """Get the routing dashboard router."""
    return router