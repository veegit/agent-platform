#!/bin/bash
set -e

# Script to optimize Azure Container Apps for cost-efficiency while maintaining functionality
# For the Agent Platform microservices architecture

echo "==== Azure Container App Cost Optimization ====" 
echo "Optimizing 4 services: API, Agent, Lifecycle, and Skill"
echo ""

# Variables
RESOURCE_GROUP="agent-platform-rg"
ENVIRONMENT="agent-platform-env"
MIN_REPLICAS=0       # Scale to zero when not in use
MAX_REPLICAS=3       # reduce to 3 max replicas

# Check Azure login status
echo "Checking Azure login status..."
az account show &>/dev/null || { echo "Please login to Azure first using 'az login'"; exit 1; }

# Verify resource group and environment exist
echo "Verifying resource group and environment..."
az group show --name $RESOURCE_GROUP &>/dev/null || { echo "Resource group $RESOURCE_GROUP not found"; exit 1; }
az containerapp env show --name $ENVIRONMENT --resource-group $RESOURCE_GROUP &>/dev/null || { echo "Container App environment $ENVIRONMENT not found"; exit 1; }

# Optimize API Service
echo ""
echo "Optimizing agent-platform-api service..."
az containerapp update --name agent-platform-api --resource-group $RESOURCE_GROUP \
  --min-replicas $MIN_REPLICAS \
  --max-replicas $MAX_REPLICAS

# Optimize Agent Service
echo ""
echo "Optimizing agent-platform-agent service..."
az containerapp update --name agent-platform-agent --resource-group $RESOURCE_GROUP \
  --min-replicas $MIN_REPLICAS \
  --max-replicas $MAX_REPLICAS

# Optimize Lifecycle Service
echo ""
echo "Optimizing agent-platform-lifecycle service..."
az containerapp update --name agent-platform-lifecycle --resource-group $RESOURCE_GROUP \
  --min-replicas $MIN_REPLICAS \
  --max-replicas $MAX_REPLICAS

# Optimize Skill Service
echo ""
echo "Optimizing agent-platform-skill service..."
az containerapp update --name agent-platform-skill --resource-group $RESOURCE_GROUP \
  --min-replicas $MIN_REPLICAS \
  --max-replicas $MAX_REPLICAS

echo ""
echo "===== Optimization Complete =====" 
echo "All services now configured to:"
echo "- Scale to zero when idle (when no traffic)"
echo "- Scale up when traffic arrives"
echo "- Maximum scale limited to 3 replicas (reduced from 10)"
echo "- Maintain full functionality with reduced costs"
echo ""
echo "Note: The first request after idle period will experience a cold start delay (typically 10-30 seconds)"
