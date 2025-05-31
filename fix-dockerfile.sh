#!/bin/bash

set -e

# Check if directory structure matches the imports
echo "Checking directory structure..."
find services -type d

echo "Building with fixed Dockerfile..."
docker build --platform linux/amd64 -t agentplatformacr.azurecr.io/agent-platform-api:fixed -f Dockerfile.fixed .
docker build --platform linux/amd64 -t agentplatformacr.azurecr.io/agent-platform-agent:fixed -f Dockerfile.fixed . --build-arg SERVICE=agent_service
docker build --platform linux/amd64 -t agentplatformacr.azurecr.io/agent-platform-lifecycle:fixed -f Dockerfile.fixed . --build-arg SERVICE=agent_lifecycle
docker build --platform linux/amd64 -t agentplatformacr.azurecr.io/agent-platform-skill:fixed -f Dockerfile.fixed . --build-arg SERVICE=skill_service

echo "Pushing fixed images..."
docker push agentplatformacr.azurecr.io/agent-platform-api:fixed
docker push agentplatformacr.azurecr.io/agent-platform-agent:fixed
docker push agentplatformacr.azurecr.io/agent-platform-lifecycle:fixed
docker push agentplatformacr.azurecr.io/agent-platform-skill:fixed

echo "Updating container apps with fixed images..."
az containerapp update --name agent-platform-api --resource-group agent-platform-rg --image agentplatformacr.azurecr.io/agent-platform-api:fixed
az containerapp update --name agent-platform-agent --resource-group agent-platform-rg --image agentplatformacr.azurecr.io/agent-platform-agent:fixed
az containerapp update --name agent-platform-lifecycle --resource-group agent-platform-rg --image agentplatformacr.azurecr.io/agent-platform-lifecycle:fixed
az containerapp update --name agent-platform-skill --resource-group agent-platform-rg --image agentplatformacr.azurecr.io/agent-platform-skill:fixed

