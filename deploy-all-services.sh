#!/bin/bash
set -e

# Login to ACR
az acr login --name agentplatformacr

# Build and tag images with platform specified for Apple Silicon compatibility
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

# Get the identity ID
IDENTITY_ID=$(az identity show --name agent-platform-identity --resource-group agent-platform-rg --query id -o tsv)

# Assign Key Vault Secrets User role to the identity
IDENTITY_PRINCIPAL_ID=$(az identity show --name agent-platform-identity --resource-group agent-platform-rg --query principalId -o tsv)
KEYVAULT_ID=$(az keyvault show --name agent-platform-kv --resource-group agent-platform-rg --query id -o tsv)
KEYVAULT_URL=$(az keyvault show --name agent-platform-kv --resource-group agent-platform-rg --query properties.vaultUri -o tsv)
az role assignment create --role "Key Vault Secrets User" --assignee $IDENTITY_PRINCIPAL_ID --scope $KEYVAULT_ID

# Get the registry credentials
ACR_USERNAME=$(az acr credential show --name agentplatformacr --resource-group agent-platform-rg --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name agentplatformacr --resource-group agent-platform-rg --query "passwords[0].value" -o tsv)

# Deploy API Service
echo "Deploying API service..."
az containerapp create \
  --name agent-platform-api \
  --resource-group agent-platform-rg \
  --environment agent-platform-env \
  --image agentplatformacr.azurecr.io/agent-platform-api:latest \
  --target-port 8000 \
  --ingress external \
  --registry-server agentplatformacr.azurecr.io \
  --registry-username $ACR_USERNAME \
  --registry-password $ACR_PASSWORD \
  --user-assigned agent-platform-identity \
  --env-vars REDIS_HOST=agent-platform-redis.redis.cache.windows.net REDIS_PORT=6380 REDIS_SSL=true \
  --secrets "redis-password=keyvaultref:https://agent-platform-kv.vault.azure.net/secrets/REDIS-PASSWORD,identityref:${IDENTITY_ID}" \
           "serpapi-api-key=keyvaultref:https://agent-platform-kv.vault.azure.net/secrets/SERP-API-KEY,identityref:${IDENTITY_ID}" \
           "groq-api-key=keyvaultref:https://agent-platform-kv.vault.azure.net/secrets/GROQ-API-KEY,identityref:${IDENTITY_ID}"

# Deploy Agent Service
echo "Deploying Agent service..."
az containerapp create \
  --name agent-platform-agent \
  --resource-group agent-platform-rg \
  --environment agent-platform-env \
  --image agentplatformacr.azurecr.io/agent-platform-agent:latest \
  --target-port 8003 \
  --ingress external \
  --registry-server agentplatformacr.azurecr.io \
  --registry-username $ACR_USERNAME \
  --registry-password $ACR_PASSWORD \
  --user-assigned agent-platform-identity \
  --env-vars REDIS_HOST=agent-platform-redis.redis.cache.windows.net REDIS_PORT=6380 REDIS_SSL=true \
  --secrets "redis-password=keyvaultref:https://agent-platform-kv.vault.azure.net/secrets/REDIS-PASSWORD,identityref:${IDENTITY_ID}" \
           "serpapi-api-key=keyvaultref:https://agent-platform-kv.vault.azure.net/secrets/SERP-API-KEY,identityref:${IDENTITY_ID}" \
           "groq-api-key=keyvaultref:https://agent-platform-kv.vault.azure.net/secrets/GROQ-API-KEY,identityref:${IDENTITY_ID}"

# Deploy Agent Lifecycle Service
echo "Deploying Agent Lifecycle service..."
az containerapp create \
  --name agent-platform-lifecycle \
  --resource-group agent-platform-rg \
  --environment agent-platform-env \
  --image agentplatformacr.azurecr.io/agent-platform-lifecycle:latest \
  --target-port 8001 \
  --ingress external \
  --registry-server agentplatformacr.azurecr.io \
  --registry-username $ACR_USERNAME \
  --registry-password $ACR_PASSWORD \
  --user-assigned agent-platform-identity \
  --env-vars REDIS_HOST=agent-platform-redis.redis.cache.windows.net REDIS_PORT=6380 REDIS_SSL=true \
  --secrets "redis-password=keyvaultref:https://agent-platform-kv.vault.azure.net/secrets/REDIS-PASSWORD,identityref:${IDENTITY_ID}" \
           "serpapi-api-key=keyvaultref:https://agent-platform-kv.vault.azure.net/secrets/SERP-API-KEY,identityref:${IDENTITY_ID}" \
           "groq-api-key=keyvaultref:https://agent-platform-kv.vault.azure.net/secrets/GROQ-API-KEY,identityref:${IDENTITY_ID}"

# Deploy Skill Service
echo "Deploying Skill service..."
az containerapp create \
  --name agent-platform-skill \
  --resource-group agent-platform-rg \
  --environment agent-platform-env \
  --image agentplatformacr.azurecr.io/agent-platform-skill:latest \
  --target-port 8002 \
  --ingress external \
  --registry-server agentplatformacr.azurecr.io \
  --registry-username $ACR_USERNAME \
  --registry-password $ACR_PASSWORD \
  --user-assigned agent-platform-identity \
  --env-vars REDIS_HOST=agent-platform-redis.redis.cache.windows.net REDIS_PORT=6380 REDIS_SSL=true \
  --secrets "redis-password=keyvaultref:https://agent-platform-kv.vault.azure.net/secrets/REDIS-PASSWORD,identityref:${IDENTITY_ID}" \
           "serpapi-api-key=keyvaultref:https://agent-platform-kv.vault.azure.net/secrets/SERP-API-KEY,identityref:${IDENTITY_ID}" \
           "groq-api-key=keyvaultref:https://agent-platform-kv.vault.azure.net/secrets/GROQ-API-KEY,identityref:${IDENTITY_ID}"

echo "All services deployed! Setting up service URLs..."

# Get the service URLs
API_URL=$(az containerapp show --name agent-platform-api --resource-group agent-platform-rg --query "properties.configuration.ingress.fqdn" -o tsv)
AGENT_URL=$(az containerapp show --name agent-platform-agent --resource-group agent-platform-rg --query "properties.configuration.ingress.fqdn" -o tsv)
LIFECYCLE_URL=$(az containerapp show --name agent-platform-lifecycle --resource-group agent-platform-rg --query "properties.configuration.ingress.fqdn" -o tsv)
SKILL_URL=$(az containerapp show --name agent-platform-skill --resource-group agent-platform-rg --query "properties.configuration.ingress.fqdn" -o tsv)

echo "==============================================="
echo "Deployment Complete! Your services are available at:"
echo "API Service: https://$API_URL"
echo "Agent Service: https://$AGENT_URL"
echo "Agent Lifecycle Service: https://$LIFECYCLE_URL"
echo "Skill Service: https://$SKILL_URL"
echo "==============================================="
echo "You can access the frontend at: https://$API_URL"

