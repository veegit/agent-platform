#!/bin/bash
set -e

echo "Building with no health probes..."
docker build --platform linux/amd64 -t agentplatformacr.azurecr.io/agent-platform-api:noprobe -f Dockerfile.noprobe .
docker build --platform linux/amd64 -t agentplatformacr.azurecr.io/agent-platform-agent:noprobe -f Dockerfile.noprobe . --build-arg SERVICE=agent_service
docker build --platform linux/amd64 -t agentplatformacr.azurecr.io/agent-platform-lifecycle:noprobe -f Dockerfile.noprobe . --build-arg SERVICE=agent_lifecycle
docker build --platform linux/amd64 -t agentplatformacr.azurecr.io/agent-platform-skill:noprobe -f Dockerfile.noprobe . --build-arg SERVICE=skill_service

echo "Pushing no-probe images..."
docker push agentplatformacr.azurecr.io/agent-platform-api:noprobe
docker push agentplatformacr.azurecr.io/agent-platform-agent:noprobe
docker push agentplatformacr.azurecr.io/agent-platform-lifecycle:noprobe
docker push agentplatformacr.azurecr.io/agent-platform-skill:noprobe

echo "Updating container apps with no-probe images..."
az containerapp update --name agent-platform-api --resource-group agent-platform-rg --image agentplatformacr.azurecr.io/agent-platform-api:noprobe
az containerapp update --name agent-platform-agent --resource-group agent-platform-rg --image agentplatformacr.azurecr.io/agent-platform-agent:noprobe
az containerapp update --name agent-platform-lifecycle --resource-group agent-platform-rg --image agentplatformacr.azurecr.io/agent-platform-lifecycle:noprobe
az containerapp update --name agent-platform-skill --resource-group agent-platform-rg --image agentplatformacr.azurecr.io/agent-platform-skill:noprobe
