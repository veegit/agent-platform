#!/bin/bash
set -e

# Default values
RESOURCE_GROUP="agent-platform-rg"
ACR_NAME="agentplatformacr"
KEYVAULT_NAME="agent-platform-kv"
ENVIRONMENT_NAME="agent-platform-env"
IDENTITY_NAME="agent-platform-identity"
SERVICES=("api" "agent" "lifecycle" "skill")
INITIAL_DEPLOY=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  key="$1"
  case $key in
    --resource-group)
      RESOURCE_GROUP="$2"
      shift
      shift
      ;;
    --acr)
      ACR_NAME="$2"
      shift
      shift
      ;;
    --keyvault)
      KEYVAULT_NAME="$2"
      shift
      shift
      ;;
    --environment)
      ENVIRONMENT_NAME="$2"
      shift
      shift
      ;;
    --identity)
      IDENTITY_NAME="$2"
      shift
      shift
      ;;
    --initial)
      INITIAL_DEPLOY=true
      shift
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

echo "════════════════════════════════════════════════════════════════"
echo "Agent Platform Azure Deployment"
echo "────────────────────────────────────────────────────────────────"
echo "Resource Group:   $RESOURCE_GROUP"
echo "ACR:              $ACR_NAME"
echo "Key Vault:        $KEYVAULT_NAME"
echo "Environment:      $ENVIRONMENT_NAME"
echo "Identity:         $IDENTITY_NAME"
echo "Initial Deploy:   $INITIAL_DEPLOY"
echo "════════════════════════════════════════════════════════════════"

# Login to ACR
echo "Logging into Azure Container Registry..."
az acr login --name $ACR_NAME

# Map service types to their module paths and ports
declare -A SERVICE_MODULES
declare -A SERVICE_PORTS
SERVICE_MODULES["api"]="services.api.main"
SERVICE_MODULES["agent"]="services.agent_service.main"
SERVICE_MODULES["lifecycle"]="services.agent_lifecycle.main"
SERVICE_MODULES["skill"]="services.skill_service.main"
SERVICE_PORTS["api"]=8000
SERVICE_PORTS["agent"]=8003
SERVICE_PORTS["lifecycle"]=8001
SERVICE_PORTS["skill"]=8002

# Build and push images for all services
echo "Building and pushing Docker images..."
for service in "${SERVICES[@]}"; do
  echo "Building $service service image..."
  if [ "$service" == "api" ]; then
    docker build --platform linux/amd64 -t $ACR_NAME.azurecr.io/agent-platform-$service:latest -f Dockerfile .
  else
    docker build --platform linux/amd64 -t $ACR_NAME.azurecr.io/agent-platform-$service:latest -f Dockerfile . --build-arg SERVICE=${service}_service
  fi
  
  echo "Pushing $service service image..."
  docker push $ACR_NAME.azurecr.io/agent-platform-$service:latest
done

# Handle identity and key vault setup if this is an initial deployment
if [ "$INITIAL_DEPLOY" = true ]; then
  echo "Creating managed identity for Key Vault access..."
  az identity create --name $IDENTITY_NAME --resource-group $RESOURCE_GROUP
  
  # Get the identity ID and principal ID
  IDENTITY_ID=$(az identity show --name $IDENTITY_NAME --resource-group $RESOURCE_GROUP --query id -o tsv)
  IDENTITY_PRINCIPAL_ID=$(az identity show --name $IDENTITY_NAME --resource-group $RESOURCE_GROUP --query principalId -o tsv)
  
  # Get Key Vault ID
  KEYVAULT_ID=$(az keyvault show --name $KEYVAULT_NAME --resource-group $RESOURCE_GROUP --query id -o tsv)
  KEYVAULT_URL=$(az keyvault show --name $KEYVAULT_NAME --resource-group $RESOURCE_GROUP --query properties.vaultUri -o tsv)
  
  # Assign Key Vault Secrets User role to the identity
  echo "Assigning Key Vault Secrets User role to the managed identity..."
  az role assignment create --role "Key Vault Secrets User" --assignee $IDENTITY_PRINCIPAL_ID --scope $KEYVAULT_ID
else
  # Just get the identity ID if redeploying
  IDENTITY_ID=$(az identity show --name $IDENTITY_NAME --resource-group $RESOURCE_GROUP --query id -o tsv)
fi

# Get the registry credentials for initial deployment
if [ "$INITIAL_DEPLOY" = true ]; then
  ACR_USERNAME=$(az acr credential show --name $ACR_NAME --resource-group $RESOURCE_GROUP --query username -o tsv)
  ACR_PASSWORD=$(az acr credential show --name $ACR_NAME --resource-group $RESOURCE_GROUP --query "passwords[0].value" -o tsv)
fi

# Deploy or update each service
for service in "${SERVICES[@]}"; do
  SERVICE_NAME="agent-platform-$service"
  SERVICE_PORT="${SERVICE_PORTS[$service]}"
  
  # Check if the service already exists
  if az containerapp show --name $SERVICE_NAME --resource-group $RESOURCE_GROUP &>/dev/null; then
    echo "Updating $service service..."
    az containerapp update \
      --name $SERVICE_NAME \
      --resource-group $RESOURCE_GROUP \
      --image $ACR_NAME.azurecr.io/agent-platform-$service:latest \
      --set-env-vars "REDIS_PASSWORD=secretref:redis-password" \
                    "SERPAPI_API_KEY=secretref:serpapi-api-key" \
                    "GEMINI_API_KEY=secretref:gemini-api-key" \
                    "REDIS_HOST=agent-platform-redis.redis.cache.windows.net" \
                    "REDIS_PORT=6380" \
                    "REDIS_SSL=true"
  else
    echo "Deploying $service service..."
    az containerapp create \
      --name $SERVICE_NAME \
      --resource-group $RESOURCE_GROUP \
      --environment $ENVIRONMENT_NAME \
      --image $ACR_NAME.azurecr.io/agent-platform-$service:latest \
      --target-port $SERVICE_PORT \
      --ingress external \
      --registry-server $ACR_NAME.azurecr.io \
      --registry-username $ACR_USERNAME \
      --registry-password $ACR_PASSWORD \
      --user-assigned $IDENTITY_NAME \
      --env-vars "REDIS_PASSWORD=secretref:redis-password" \
                "SERPAPI_API_KEY=secretref:serpapi-api-key" \
                "GROQ_API_KEY=secretref:groq-api-key" \
                "REDIS_HOST=agent-platform-redis.redis.cache.windows.net" \
                "REDIS_PORT=6380" \
                "REDIS_SSL=true" \
      --secrets "redis-password=keyvaultref:https://$KEYVAULT_NAME.vault.azure.net/secrets/REDIS-PASSWORD,identityref:${IDENTITY_ID}" \
               "serpapi-api-key=keyvaultref:https://$KEYVAULT_NAME.vault.azure.net/secrets/SERP-API-KEY,identityref:${IDENTITY_ID}" \
               "gemini-api-key=keyvaultref:https://$KEYVAULT_NAME.vault.azure.net/secrets/GEMINI-API-KEY,identityref:${IDENTITY_ID}"
  fi
done

# Get the service URLs
echo "Getting service URLs..."
API_URL=$(az containerapp show --name agent-platform-api --resource-group $RESOURCE_GROUP --query "properties.configuration.ingress.fqdn" -o tsv)
AGENT_URL=$(az containerapp show --name agent-platform-agent --resource-group $RESOURCE_GROUP --query "properties.configuration.ingress.fqdn" -o tsv 2>/dev/null || echo "Not deployed")
LIFECYCLE_URL=$(az containerapp show --name agent-platform-lifecycle --resource-group $RESOURCE_GROUP --query "properties.configuration.ingress.fqdn" -o tsv 2>/dev/null || echo "Not deployed")
SKILL_URL=$(az containerapp show --name agent-platform-skill --resource-group $RESOURCE_GROUP --query "properties.configuration.ingress.fqdn" -o tsv 2>/dev/null || echo "Not deployed")

# Configure service URLs for cross-service communication
for service in "${SERVICES[@]}"; do
  SERVICE_NAME="agent-platform-$service"
  
  echo "Configuring service URLs for $service service..."
  az containerapp update \
    --name $SERVICE_NAME \
    --resource-group $RESOURCE_GROUP \
    --set-env-vars "API_SERVICE_URL=https://$API_URL" \
                  "AGENT_SERVICE_URL=https://$AGENT_URL" \
                  "AGENT_LIFECYCLE_SERVICE_URL=https://$LIFECYCLE_URL" \
                  "SKILL_SERVICE_URL=https://$SKILL_URL"
done

echo "════════════════════════════════════════════════════════════════"
echo "Deployment Complete! Your services are available at:"
echo "API Service:           https://$API_URL"
echo "Agent Service:         https://$AGENT_URL"
echo "Agent Lifecycle Service: https://$LIFECYCLE_URL"
echo "Skill Service:         https://$SKILL_URL"
echo "════════════════════════════════════════════════════════════════"
echo "You can access the frontend at: https://$API_URL"
echo "Note: The first request after idle period will experience a cold start delay (typically 10-30 seconds)"
