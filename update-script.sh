#!/bin/bash

# Set service URLs as environment variables for all services
API_URL="https://agent-platform-api.purplewater-c0416f2a.eastus.azurecontainerapps.io"
AGENT_URL="https://agent-platform-agent.purplewater-c0416f2a.eastus.azurecontainerapps.io"
LIFECYCLE_URL="https://agent-platform-lifecycle.purplewater-c0416f2a.eastus.azurecontainerapps.io"
SKILL_URL="https://agent-platform-skill.purplewater-c0416f2a.eastus.azurecontainerapps.io"

# Update API service with proper service URLs
az containerapp update --name agent-platform-api --resource-group agent-platform-rg \
  --set-env-vars "REDIS_HOST=agent-platform-redis.redis.cache.windows.net" \
               "REDIS_PORT=6380" \
               "REDIS_SSL=true" \
               "AGENT_SERVICE_URL=$AGENT_URL" \
               "AGENT_LIFECYCLE_SERVICE_URL=$LIFECYCLE_URL" \
               "SKILL_SERVICE_URL=$SKILL_URL" \
               "API_SERVICE_URL=$API_URL"

# Update Agent service with proper service URLs
az containerapp update --name agent-platform-agent --resource-group agent-platform-rg \
  --set-env-vars "REDIS_HOST=agent-platform-redis.redis.cache.windows.net" \
               "REDIS_PORT=6380" \
               "REDIS_SSL=true" \
               "AGENT_SERVICE_URL=$AGENT_URL" \
               "AGENT_LIFECYCLE_SERVICE_URL=$LIFECYCLE_URL" \
               "SKILL_SERVICE_URL=$SKILL_URL" \
               "API_SERVICE_URL=$API_URL"

# Update Lifecycle service with proper service URLs
az containerapp update --name agent-platform-lifecycle --resource-group agent-platform-rg \
  --set-env-vars "REDIS_HOST=agent-platform-redis.redis.cache.windows.net" \
               "REDIS_PORT=6380" \
               "REDIS_SSL=true" \
               "AGENT_SERVICE_URL=$AGENT_URL" \
               "AGENT_LIFECYCLE_SERVICE_URL=$LIFECYCLE_URL" \
               "SKILL_SERVICE_URL=$SKILL_URL" \
               "API_SERVICE_URL=$API_URL"

# Update Skill service with proper service URLs
az containerapp update --name agent-platform-skill --resource-group agent-platform-rg \
  --set-env-vars "REDIS_HOST=agent-platform-redis.redis.cache.windows.net" \
               "REDIS_PORT=6380" \
               "REDIS_SSL=true" \
               "AGENT_SERVICE_URL=$AGENT_URL" \
               "AGENT_LIFECYCLE_SERVICE_URL=$LIFECYCLE_URL" \
               "SKILL_SERVICE_URL=$SKILL_URL" \
               "API_SERVICE_URL=$API_URL"
