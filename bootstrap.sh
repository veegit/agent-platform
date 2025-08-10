#!/bin/bash

# Agent Platform Bootstrap Script
# This script recreates agents and their delegate mappings from embedded configuration
# Usage: ./bootstrap.sh <hostname>

set -e  # Exit on any error

# Default values
DEFAULT_PORT="8001"

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
    echo "Usage: $0 <hostname>"
    echo ""
    echo "Arguments:"
    echo "  hostname     - The hostname/IP where the agent lifecycle service is running"
    echo ""
    echo "Examples:"
    echo "  $0 localhost"
    echo "  $0 192.168.1.100"
    echo ""
    echo "The script will:"
    echo "  1. Create all agents from embedded configuration"
    echo "  2. Set up delegate domain mappings"
    echo "  3. Activate all agents"
}

# Check arguments
if [ $# -ne 1 ]; then
    show_usage
    exit 1
fi

HOSTNAME="$1"
BASE_URL="http://${HOSTNAME}:${DEFAULT_PORT}"

# Embedded agent configuration
get_agent_config() {
    cat << 'EOF'
{
  "agents": [
    {
      "agent_id": "supervisor_agent",
      "status": "active",
      "config": {
        "agent_id": "supervisor_agent",
        "persona": {
          "name": "Supervisor Agent",
          "description": "Coordinates specialized agents to assist with complex queries",
          "goals": [
            "Provide accurate information",
            "Delegate to domain experts when necessary"
          ],
          "constraints": [
            "Only use verified sources",
            "Respect user privacy"
          ],
          "tone": "helpful and friendly",
          "system_prompt": "You manage a team of domain experts. Coordinate with them only when necessary and avoid mentioning them unless relevant."
        },
        "llm": {
          "model_name": "gemini-2.5-flash",
          "temperature": 0.7,
          "max_tokens": 2000,
          "top_p": null,
          "frequency_penalty": null,
          "presence_penalty": null,
          "provider": "gemini"
        },
        "skills": [],
        "memory": {
          "max_messages": 50,
          "summarize_after": 20,
          "long_term_memory_enabled": true,
          "key_fact_extraction_enabled": true
        },
        "is_supervisor": true,
        "default_skill_params": {},
        "additional_config": {}
      },
      "created_at": "2025-08-05T04:17:07.064023",
      "updated_at": "2025-08-05T04:17:07.064023",
      "created_by": null,
      "domain": null,
      "keywords": []
    },
    {
      "agent_id": "research-agent",
      "status": "active",
      "config": {
        "agent_id": "research-agent",
        "persona": {
          "name": "Research Agent",
          "description": "Helps with research and summarizing information",
          "goals": [
            "Provide thorough answers",
            "Find relevant sources"
          ],
          "constraints": [
            "Avoid speculation"
          ],
          "tone": "informative",
          "system_prompt": "You are an expert research assistant."
        },
        "llm": {
          "model_name": "gemini-2.5-flash",
          "temperature": 0.7,
          "max_tokens": 2000,
          "top_p": null,
          "frequency_penalty": null,
          "presence_penalty": null,
          "provider": "gemini"
        },
        "skills": [
          "ask-follow-up",
          "summarize-text",
          "web-search"
        ],
        "memory": {
          "max_messages": 50,
          "summarize_after": 20,
          "long_term_memory_enabled": true,
          "key_fact_extraction_enabled": true
        },
        "is_supervisor": false,
        "default_skill_params": {},
        "additional_config": {}
      },
      "created_at": "2025-08-05T04:17:00.578893",
      "updated_at": "2025-08-05T04:17:00.578894",
      "created_by": null,
      "domain": "research",
      "keywords": [
        "research",
        "analysis",
        "sources"
      ]
    },
    {
      "agent_id": "finance-agent",
      "status": "active",
      "config": {
        "agent_id": "finance-agent",
        "persona": {
          "name": "Finance Agent",
          "description": "Provides stock prices and market updates",
          "goals": [
            "Fetch real-time market data"
          ],
          "constraints": [
            "No investment advice"
          ],
          "tone": "professional",
          "system_prompt": "You specialize in financial data and stock information."
        },
        "llm": {
          "model_name": "gemini-2.5-flash",
          "temperature": 0.7,
          "max_tokens": 2000,
          "top_p": null,
          "frequency_penalty": null,
          "presence_penalty": null,
          "provider": "gemini"
        },
        "skills": [
          "finance"
        ],
        "memory": {
          "max_messages": 50,
          "summarize_after": 20,
          "long_term_memory_enabled": true,
          "key_fact_extraction_enabled": true
        },
        "is_supervisor": false,
        "default_skill_params": {},
        "additional_config": {}
      },
      "created_at": "2025-08-05T04:16:27.630000",
      "updated_at": "2025-08-05T04:16:27.630002",
      "created_by": null,
      "domain": "finance",
      "keywords": [
        "stocks",
        "market",
        "investment"
      ]
    }
  ],
  "total": 3
}
EOF
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
echo ""

# Test connection to agent lifecycle service
print_info "Testing connection to agent lifecycle service..."
if ! curl -s -f "$BASE_URL/health" > /dev/null; then
    print_error "Cannot connect to agent lifecycle service at $BASE_URL"
    print_error "Please ensure the service is running and accessible"
    exit 1
fi
print_success "Connected to agent lifecycle service"

# Get embedded configuration and parse agents
CONFIG_JSON=$(get_agent_config)
AGENT_COUNT=$(echo "$CONFIG_JSON" | jq '.agents | length')
print_info "Found $AGENT_COUNT agents in embedded configuration"
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
    else
        # Check if agent already exists
        if echo "$RESPONSE" | grep -q "already exists\|duplicate"; then
            print_warning "Agent $AGENT_ID already exists, skipping creation"
        else
            print_error "Failed to create agent $AGENT_ID"
            print_error "Response: $RESPONSE"
            continue
        fi
    fi
    
    # Activate the agent if it should be active
    if [ "$STATUS" = "active" ]; then
        print_info "Activating agent: $AGENT_ID"
        
        ACTIVATE_REQUEST='{"status": "active"}'
        ACTIVATE_RESPONSE=$(curl -s -X PUT "$BASE_URL/agents/$AGENT_ID/status" \
            -H "Content-Type: application/json" \
            -d "$ACTIVATE_REQUEST")
        
        if echo "$ACTIVATE_RESPONSE" | jq -e '.success' > /dev/null 2>&1; then
            print_success "Activated agent: $AGENT_ID"
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

# Show Redis delegate verification command
echo ""
print_info "To verify delegate setup in Redis, run:"
echo "docker exec -it agent-platform-redis-1 redis-cli keys \"delegate:*\""
