#!/bin/bash

# Agent Platform Bootstrap Script
# This script recreates agents and their delegate mappings from saved configuration
# Usage: ./bootstrap.sh <hostname> [--recreate]

set -e  # Exit on any error

# Default values
DEFAULT_PORT="8001"
AGENTS_FILE="agents.json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to show usage
show_usage() {
    echo "Usage: $0 <hostname> [--recreate]"
    echo ""
    echo "Arguments:"
    echo "  hostname     - The hostname/IP where the agent lifecycle service is running"
    echo "  --recreate   - Delete existing agents before creating new ones"
    echo ""
    echo "Examples:"
    echo "  $0 localhost                  # Create agents from $AGENTS_FILE (skip if exist)"
    echo "  $0 localhost --recreate       # Delete and recreate all agents"
    echo "  $0 192.168.1.100 --recreate"
    echo ""
    echo "The script will:"
    echo "  1. Load agent configuration from $AGENTS_FILE"
    echo "  2. Optionally delete existing agents (with --recreate)"
    echo "  3. Create all agents from configuration"
    echo "  4. Set up delegate domain mappings"
    echo "  5. Activate all agents"
}

# Check arguments
if [ $# -lt 1 ] || [ $# -gt 2 ]; then
    show_usage
    exit 1
fi

HOSTNAME="$1"
RECREATE_MODE=false

# Parse optional --recreate flag
if [ $# -eq 2 ] && [ "$2" = "--recreate" ]; then
    RECREATE_MODE=true
elif [ $# -eq 2 ]; then
    print_error "Invalid argument: $2"
    show_usage
    exit 1
fi

BASE_URL="http://${HOSTNAME}:${DEFAULT_PORT}"

# Function to load agent configuration from file
get_agent_config() {
    if [ -f "$AGENTS_FILE" ]; then
        print_info "Loading agent configuration from $AGENTS_FILE" >&2
        cat "$AGENTS_FILE"
    else
        print_error "$AGENTS_FILE not found. Please create the file with agent configuration."
        print_info "Expected file format:"
        print_info '{'
        print_info '  "agents": ['
        print_info '    {'
        print_info '      "agent_id": "agent_name",'
        print_info '      "status": "active",'
        print_info '      "config": { ... },'
        print_info '      "domain": "optional_domain",'
        print_info '      "keywords": ["keyword1", "keyword2"]'
        print_info '    }'
        print_info '  ],'
        print_info '  "total": 1'
        print_info '}'
        exit 1
    fi
}

# Function to delete an existing agent
delete_agent() {
    local agent_id="$1"
    print_info "Deleting existing agent: $agent_id"
    
    DELETE_RESPONSE=$(curl -s -X DELETE "$BASE_URL/agents/$agent_id" \
        -H "Content-Type: application/json")
    
    if echo "$DELETE_RESPONSE" | jq -e '.success' > /dev/null 2>&1; then
        print_success "Deleted agent: $agent_id"
    elif echo "$DELETE_RESPONSE" | grep -q "not found\|404"; then
        print_info "Agent $agent_id does not exist, skipping deletion"
    else
        print_warning "Failed to delete agent $agent_id (may not exist)"
        print_info "Response: $DELETE_RESPONSE"
    fi
}

# Function to list all existing agents
list_existing_agents() {
    curl -s "$BASE_URL/agents" | jq -r '.agents[].agent_id' 2>/dev/null || echo ""
}

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    print_error "jq is required but not installed. Please install jq first."
    exit 1
fi

# Check if curl is installed
if ! command -v curl &> /dev/null; then
    print_error "curl is required but not installed. Please install curl first."
    exit 1
fi

print_info "Starting Agent Platform Bootstrap"
print_info "Hostname: $HOSTNAME"
print_info "Base URL: $BASE_URL"
print_info "Configuration file: $AGENTS_FILE"
if $RECREATE_MODE; then
    print_warning "RECREATE MODE: Will delete existing agents before creating new ones"
fi
echo ""

# Test connection to agent lifecycle service
print_info "Testing connection to agent lifecycle service..."
if ! curl -s -f "$BASE_URL/health" > /dev/null; then
    print_error "Cannot connect to agent lifecycle service at $BASE_URL"
    print_error "Please ensure the service is running and accessible"
    exit 1
fi
print_success "Connected to agent lifecycle service"

# Handle recreate mode - delete existing agents first
if $RECREATE_MODE; then
    print_info "Recreate mode enabled - deleting all existing agents..."
    EXISTING_AGENTS=$(list_existing_agents)
    
    if [ -n "$EXISTING_AGENTS" ]; then
        echo "$EXISTING_AGENTS" | while read -r agent_id; do
            if [ -n "$agent_id" ]; then
                delete_agent "$agent_id"
            fi
        done
        
        # Small delay to allow deletions to complete
        sleep 2
        print_success "All existing agents deleted"
    else
        print_info "No existing agents found to delete"
    fi
    echo ""
fi

# Get configuration and parse agents
CONFIG_JSON=$(get_agent_config)
if [ -z "$CONFIG_JSON" ] || ! echo "$CONFIG_JSON" | jq empty > /dev/null 2>&1; then
    print_error "Invalid or empty JSON configuration"
    exit 1
fi

AGENT_COUNT=$(echo "$CONFIG_JSON" | jq '.agents | length')
print_info "Found $AGENT_COUNT agents in configuration"
echo ""

# Create each agent
for i in $(seq 0 $((AGENT_COUNT - 1))); do
    # Extract agent data from embedded config
    AGENT_ID=$(echo "$CONFIG_JSON" | jq -r ".agents[$i].agent_id")
    STATUS=$(echo "$CONFIG_JSON" | jq -r ".agents[$i].status")
    CONFIG=$(echo "$CONFIG_JSON" | jq ".agents[$i].config")
    DOMAIN=$(echo "$CONFIG_JSON" | jq -r ".agents[$i].domain // empty")
    KEYWORDS=$(echo "$CONFIG_JSON" | jq -r ".agents[$i].keywords[]? // empty" | tr '\n' ',' | sed 's/,$//')
    
    print_info "Creating agent: $AGENT_ID"
    
    # Prepare create agent request
    CREATE_REQUEST=$(jq -n \
        --argjson config "$CONFIG" \
        --arg domain "$DOMAIN" \
        --arg keywords "$KEYWORDS" \
        '{
            config: $config,
            created_by: "bootstrap_script"
        } + 
        (if $domain != "" then {domain: $domain} else {} end) +
        (if $keywords != "" then {keywords: ($keywords | split(","))} else {} end)')
    
    # Create the agent
    RESPONSE=$(curl -s -X POST "$BASE_URL/agents" \
        -H "Content-Type: application/json" \
        -d "$CREATE_REQUEST")
    
    # Check if creation was successful
    if echo "$RESPONSE" | jq -e '.agent_id' > /dev/null 2>&1; then
        print_success "Created agent: $AGENT_ID"
        
        # Show delegate info if present
        RESPONSE_DOMAIN=$(echo "$RESPONSE" | jq -r '.domain // empty')
        RESPONSE_KEYWORDS=$(echo "$RESPONSE" | jq -r '.keywords[]? // empty' | tr '\n' ',' | sed 's/,$//')
        
        if [ -n "$RESPONSE_DOMAIN" ]; then
            print_info "  └─ Delegate domain: $RESPONSE_DOMAIN"
            if [ -n "$RESPONSE_KEYWORDS" ]; then
                print_info "  └─ Keywords: $RESPONSE_KEYWORDS"
            fi
        fi
        AGENT_CREATED=true
    else
        # Check if agent already exists
        if echo "$RESPONSE" | grep -q "already exists\|duplicate"; then
            print_warning "Agent $AGENT_ID already exists, skipping creation"
            AGENT_CREATED=false
        else
            print_error "Failed to create agent $AGENT_ID"
            print_error "Response: $RESPONSE"
            continue
        fi
    fi
    
    # Activate the agent if it should be active (for both new and existing agents)
    if [ "$STATUS" = "active" ]; then
        print_info "Activating agent: $AGENT_ID"
        
        ACTIVATE_REQUEST='{"status": "active"}'
        ACTIVATE_RESPONSE=$(curl -s -X PUT "$BASE_URL/agents/$AGENT_ID/status" \
            -H "Content-Type: application/json" \
            -d "$ACTIVATE_REQUEST")
        
        if echo "$ACTIVATE_RESPONSE" | jq -e '.success' > /dev/null 2>&1; then
            print_success "Activated agent: $AGENT_ID"
        elif echo "$ACTIVATE_RESPONSE" | jq -e '.message' > /dev/null 2>&1; then
            MESSAGE=$(echo "$ACTIVATE_RESPONSE" | jq -r '.message')
            print_info "Agent $AGENT_ID: $MESSAGE"
        else
            print_warning "Failed to activate agent $AGENT_ID (may already be active)"
        fi
    fi
    
    echo ""
done

# Verify the setup
print_info "Verifying agent setup..."
FINAL_AGENTS=$(curl -s "$BASE_URL/agents" | jq '.agents | length')
print_success "Total agents created: $FINAL_AGENTS"

# Show delegate summary
print_info "Delegate domain summary:"
DELEGATES=$(curl -s "$BASE_URL/agents" | jq -r '.agents[] | select(.domain != null) | "\(.agent_id): \(.domain) [\(.keywords | join(", "))]"')

if [ -n "$DELEGATES" ]; then
    echo "$DELEGATES" | while read -r line; do
        print_info "  └─ $line"
    done
else
    print_info "  └─ No delegate domains configured"
fi

echo ""
print_success "Bootstrap completed successfully!"
print_info "You can now test your agents by sending messages to the platform"

# Show additional verification commands
echo ""
print_info "Verification commands:"
print_info "  Delegate setup in Redis:"
echo "  docker exec -it agent-platform-redis-1 redis-cli keys \"delegate:*\""
echo ""
print_info "  Model Router statistics:"
echo "  curl -s http://$HOSTNAME:8000/routing/stats | jq"
echo ""
print_info "  Routing health check:"
echo "  curl -s http://$HOSTNAME:8000/routing/health | jq"
echo ""
print_info "  Agent list:"
echo "  curl -s http://$HOSTNAME:8000/agents | jq"

# Show configuration source
echo ""
print_info "Agent configuration loaded from: $AGENTS_FILE"
print_info "To update agents: modify $AGENTS_FILE and run this script with --recreate"
print_info "To save current configuration: curl -s $BASE_URL/agents > $AGENTS_FILE"
