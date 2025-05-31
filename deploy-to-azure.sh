#!/bin/bash
set -e

# Login to ACR
az acr login --name agentplatformacr

# Build and tag images
# Update your docker build commands to specify the platform
docker build --platform linux/amd64 -t agentplatformacr.azurecr.io/agent-platform-api:latest -f Dockerfile .
docker build --platform linux/amd64 -t agentplatformacr.azurecr.io/agent-platform-agent:latest -f Dockerfile . --build-arg SERVICE=agent_service
docker build --platform linux/amd64 -t agentplatformacr.azurecr.io/agent-platform-lifecycle:latest -f Dockerfile . --build-arg SERVICE=agent_lifecycle
docker build --platform linux/amd64 -t agentplatformacr.azurecr.io/agent-platform-skill:latest -f Dockerfile . --build-arg SERVICE=skill_service

# Push images to ACR
docker push agentplatformacr.azurecr.io/agent-platform-api:latest
docker push agentplatformacr.azurecr.io/agent-platform-agent:latest
docker push agentplatformacr.azurecr.io/agent-platform-lifecycle:latest
docker push agentplatformacr.azurecr.io/agent-platform-skill:latest

# Create identity for Key Vault access
az identity create --name agent-platform-identity --resource-group agent-platform-rg

# Assign Key Vault Secrets User role to the identity
IDENTITY_PRINCIPAL_ID=$(az identity show --name agent-platform-identity --resource-group agent-platform-rg --query principalId -o tsv)
KEYVAULT_ID=$(az keyvault show --name agent-platform-kv --resource-group agent-platform-rg --query id -o tsv)
KEYVAULT_URL=$(az keyvault show --name agent-platform-kv --resource-group agent-platform-rg --query properties.vaultUri -o tsv)
az role assignment create --role "Key Vault Secrets User" --assignee $IDENTITY_PRINCIPAL_ID --scope $KEYVAULT_ID

# Deploy Container Apps with Azure identity
echo "Deploying API service..."
# Get the identity ID
IDENTITY_ID=$(az identity show --name agent-platform-identity --resource-group agent-platform-rg --query id -o tsv)

# Update the containerapp create command
az containerapp create \
  --name agent-platform-api \
  --resource-group agent-platform-rg \
  --environment agent-platform-env \
  --image agentplatformacr.azurecr.io/agent-platform-api:latest \
  --target-port 8000 \
  --ingress external \
  --registry-server agentplatformacr.azurecr.io \
  --user-assigned agent-platform-identity \
  --env-vars REDIS_HOST=agent-platform-redis.redis.cache.windows.net REDIS_PORT=6380 REDIS_SSL=true \
  --secrets "redis-password=keyvaultref:https://agent-platform-kv.vault.azure.net/secrets/REDIS-PASSWORD,identityref:${IDENTITY_ID}" \
         "serpapi-api-key=keyvaultref:https://agent-platform-kv.vault.azure.net/secrets/SERP-API-KEY,identityref:${IDENTITY_ID}" \
         "groq-api-key=keyvaultref:https://agent-platform-kv.vault.azure.net/secrets/GROQ-API-KEY,identityref:${IDENTITY_ID}"
echo "Deployment complete!"

