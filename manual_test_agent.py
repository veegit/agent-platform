#!/usr/bin/env python3
"""
Test script to create and interact with an agent.
"""

import asyncio
import json
import httpx

async def create_agent():
    """Create a test agent."""
    url = "http://localhost:8001/agents"
    data = {
        "config": {
            "persona": {
                "name": "Test Agent",
                "description": "A test agent for the platform",
                "goals": ["Help with testing"],
                "constraints": ["Be helpful"],
                "tone": "friendly",
                "system_prompt": "You are a test agent. Be helpful."
            },
            "reasoning_model": "llama3_70b",
            "skills": ["web-search", "summarize-text", "ask-follow-up"],
            "memory": {
                "max_messages": 50,
                "summarize_after": 20,
                "long_term_memory_enabled": True,
                "key_fact_extraction_enabled": True
            }
        },
        "created_by": "test_user",
        "domain": "test",
        "keywords": ["test"]
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=data, timeout=30.0)
        
        if response.status_code == 201:
            agent_data = response.json()
            print(f"Created agent: {agent_data['agent_id']}")
            return agent_data
        else:
            print(f"Failed to create agent: {response.status_code} - {response.text}")
            return None

async def activate_agent(agent_id):
    """Activate the agent."""
    url = f"http://localhost:8001/agents/{agent_id}/status"
    data = {
        "status": "active"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.put(url, json=data, timeout=30.0)
        
        if response.status_code == 200:
            status_data = response.json()
            print(f"Activated agent: {status_data['agent_id']}")
            return True
        else:
            print(f"Failed to activate agent: {response.status_code} - {response.text}")
            return False

async def start_conversation(agent_id):
    """Start a conversation with the agent."""
    url = "http://localhost:8000/conversations"
    data = {
        "agent_id": agent_id,
        "user_id": "test_user",
        "initial_message": "Hello! Can you help me?",
        "metadata": {
            "title": "Test Conversation"
        }
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=data, timeout=60.0)
        
        if response.status_code == 200:
            conv_data = response.json()
            print(f"Started conversation: {conv_data['id']}")
            print(f"Agent response: {conv_data.get('last_message', {}).get('content')}")
            return conv_data
        else:
            print(f"Failed to start conversation: {response.status_code} - {response.text}")
            return None

async def main():
    """Main function."""
    print("Testing the Agent Platform")
    
    # First, try to use the default fallback agent
    default_agent_id = "default-agent"

    print("Starting conversation with default agent...")
    demo_conv = await start_conversation(default_agent_id)
    
    if not demo_conv:
        print("Creating new agent...")
        agent_data = await create_agent()
        
        if agent_data:
            agent_id = agent_data["agent_id"]
            print("Activating agent...")
            
            if await activate_agent(agent_id):
                print("Starting conversation with new agent...")
                await start_conversation(agent_id)
                
                # Print agent ID for future reference
                print(f"\nUse this agent ID for future tests: {agent_id}")
    
    print("Test completed")

if __name__ == "__main__":
    asyncio.run(main())
