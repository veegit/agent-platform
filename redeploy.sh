#!/bin/bash
set -e
           
echo "Building and deploying updated Agent Platform images..."

# Login to ACR
az acr login --name agentplatformacr

# Build and tag images with platform specified for Apple Silicon compatibility
echo "Building API service image..."
docker build --platform linux/amd64 -t agentplatformacr.azurecr.io/agent-platform-api:latest -f Dockerfile .

echo "Building Agent service image..."
docker build --platform linux/amd64 -t agentplatformacr.azurecr.io/agent-platform-agent:latest -f Dockerfile . --build-arg SERVICE=agent_service

echo "Building Lifecycle service image..."
docker build --platform linux/amd64 -t agentplatformacr.azurecr.io/agent-platform-lifecycle:latest -f Dockerfile . --build-arg SERVICE=agent_lifecycle

echo "Building Skill service image..."
docker build --platform linux/amd64 -t agentplatformacr.azurecr.io/agent-platform-skill:latest -f Dockerfile . --build-arg SERVICE=skill_service

# Push images to ACR
echo "Pushing images to ACR..."
docker push agentplatformacr.azurecr.io/agent-platform-api:latest
docker push agentplatformacr.azurecr.io/agent-platform-agent:latest
docker push agentplatformacr.azurecr.io/agent-platform-lifecycle:latest
docker push agentplatformacr.azurecr.io/agent-platform-skill:latest

# Get the identity ID
echo "Getting identity and registry credentials..."
IDENTITY_ID=$(az identity show --name agent-platform-identity --resource-group agent-platform-rg --query id -o tsv)
ACR_USERNAME=$(az acr credential show --name agentplatformacr --resource-group agent-platform-rg --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name agentplatformacr --resource-group agent-platform-rg --query "passwords[0].value" -o tsv)

# Update the API service
echo "Updating API service..."
az containerapp update \
  --name agent-platform-api \
  --resource-group agent-platform-rg \
  --image agentplatformacr.azurecr.io/agent-platform-api:latest \
  --set-env-vars "REDIS_PASSWORD=secretref:redis-password" \
                "SERPAPI_API_KEY=secretref:serpapi-api-key" \
                "GROQ_API_KEY=secretref:groq-api-key" \
                "REDIS_HOST=agent-platform-redis.redis.cache.windows.net" \
                "REDIS_PORT=6380" \
                "REDIS_SSL=true"

# Check if agent service exists
if ! az containerapp show --name agent-platform-agent --resource-group agent-platform-rg &>/dev/null; then
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
    --env-vars "REDIS_PASSWORD=secretref:redis-password" \
              "SERPAPI_API_KEY=secretref:serpapi-api-key" \
              "GROQ_API_KEY=secretref:groq-api-key" \
              "REDIS_HOST=agent-platform-redis.redis.cache.windows.net" \
              "REDIS_PORT=6380" \
              "REDIS_SSL=true" \
    --secrets "redis-password=keyvaultref:https://agent-platform-kv.vault.azure.net/secrets/REDIS-PASSWORD,identityref:${IDENTITY_ID}" \
            "serpapi-api-key=keyvaultref:https://agent-platform-kv.vault.azure.net/secrets/SERP-API-KEY,identityref:${IDENTITY_ID}" \
            "groq-api-key=keyvaultref:https://agent-platform-kv.vault.azure.net/secrets/GROQ-API-KEY,identityref:${IDENTITY_ID}"
else
  echo "Updating Agent service..."
  az containerapp update \
    --name agent-platform-agent \
    --resource-group agent-platform-rg \
    --image agentplatformacr.azurecr.io/agent-platform-agent:latest \
    --set-env-vars "REDIS_PASSWORD=secretref:redis-password" \
                  "SERPAPI_API_KEY=secretref:serpapi-api-key" \
                  "GROQ_API_KEY=secretref:groq-api-key" \
                  "REDIS_HOST=agent-platform-redis.redis.cache.windows.net" \
                  "REDIS_PORT=6380" \
                  "REDIS_SSL=true"
fi

# Check if lifecycle service exists
if ! az containerapp show --name agent-platform-lifecycle --resource-group agent-platform-rg &>/dev/null; then
  echo "Deploying Lifecycle service..."
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
    --env-vars "REDIS_PASSWORD=secretref:redis-password" \
              "SERPAPI_API_KEY=secretref:serpapi-api-key" \
              "GROQ_API_KEY=secretref:groq-api-key" \
              "REDIS_HOST=agent-platform-redis.redis.cache.windows.net" \
              "REDIS_PORT=6380" \
              "REDIS_SSL=true" \
    --secrets "redis-password=keyvaultref:https://agent-platform-kv.vault.azure.net/secrets/REDIS-PASSWORD,identityref:${IDENTITY_ID}" \
            "serpapi-api-key=keyvaultref:https://agent-platform-kv.vault.azure.net/secrets/SERP-API-KEY,identityref:${IDENTITY_ID}" \
            "groq-api-key=keyvaultref:https://agent-platform-kv.vault.azure.net/secrets/GROQ-API-KEY,identityref:${IDENTITY_ID}"
else
  echo "Updating Lifecycle service..."
  az containerapp update \
    --name agent-platform-lifecycle \
    --resource-group agent-platform-rg \
    --image agentplatformacr.azurecr.io/agent-platform-lifecycle:latest \
    --set-env-vars "REDIS_PASSWORD=secretref:redis-password" \
                  "SERPAPI_API_KEY=secretref:serpapi-api-key" \
                  "GROQ_API_KEY=secretref:groq-api-key" \
                  "REDIS_HOST=agent-platform-redis.redis.cache.windows.net" \
                  "REDIS_PORT=6380" \
                  "REDIS_SSL=true"
fi

# Check if skill service exists
if ! az containerapp show --name agent-platform-skill --resource-group agent-platform-rg &>/dev/null; then
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
    --env-vars "REDIS_PASSWORD=secretref:redis-password" \
              "SERPAPI_API_KEY=secretref:serpapi-api-key" \
              "GROQ_API_KEY=secretref:groq-api-key" \
              "REDIS_HOST=agent-platform-redis.redis.cache.windows.net" \
              "REDIS_PORT=6380" \
              "REDIS_SSL=true" \
    --secrets "redis-password=keyvaultref:https://agent-platform-kv.vault.azure.net/secrets/REDIS-PASSWORD,identityref:${IDENTITY_ID}" \
            "serpapi-api-key=keyvaultref:https://agent-platform-kv.vault.azure.net/secrets/SERP-API-KEY,identityref:${IDENTITY_ID}" \
            "groq-api-key=keyvaultref:https://agent-platform-kv.vault.azure.net/secrets/GROQ-API-KEY,identityref:${IDENTITY_ID}"
else
  echo "Updating Skill service..."
  az containerapp update \
    --name agent-platform-skill \
    --resource-group agent-platform-rg \
    --image agentplatformacr.azurecr.io/agent-platform-skill:latest \
    --set-env-vars "REDIS_PASSWORD=secretref:redis-password" \
                  "SERPAPI_API_KEY=secretref:serpapi-api-key" \
                  "GROQ_API_KEY=secretref:groq-api-key" \
                  "REDIS_HOST=agent-platform-redis.redis.cache.windows.net" \
                  "REDIS_PORT=6380" \
                  "REDIS_SSL=true"
fi

# Get the service URLs
echo "Getting service URLs..."
API_URL=$(az containerapp show --name agent-platform-api --resource-group agent-platform-rg --query "properties.configuration.ingress.fqdn" -o tsv)
AGENT_URL=$(az containerapp show --name agent-platform-agent --resource-group agent-platform-rg --query "properties.configuration.ingress.fqdn" -o tsv 2>/dev/null || echo "Not deployed")
LIFECYCLE_URL=$(az containerapp show --name agent-platform-lifecycle --resource-group agent-platform-rg --query "properties.configuration.ingress.fqdn" -o tsv 2>/dev/null || echo "Not deployed")
SKILL_URL=$(az containerapp show --name agent-platform-skill --resource-group agent-platform-rg --query "properties.configuration.ingress.fqdn" -o tsv 2>/dev/null || echo "Not deployed")

echo "==============================================="
echo "Deployment Complete! Your services are available at:"
echo "API Service: https://$API_URL"
echo "Agent Service: https://$AGENT_URL"
echo "Agent Lifecycle Service: https://$LIFECYCLE_URL"
echo "Skill Service: https://$SKILL_URL"
echo "==============================================="
echo "You can access the frontend at: https://$API_URL"