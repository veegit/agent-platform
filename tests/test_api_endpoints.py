import sys
import types
import asyncio
import importlib
from datetime import datetime

from tests.helpers import FakeRedis

# Minimal httpx stub for module imports
fake_httpx = types.ModuleType('httpx')
class DummyAsyncClient:
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc, tb):
        pass
    async def post(self, *a, **k):
        return DummyResponse({})
    async def get(self, *a, **k):
        return DummyResponse({})
class DummyResponse:
    def __init__(self, data, status_code=200):
        self.status_code = status_code
        self._data = data
    def json(self):
        return self._data
fake_httpx.AsyncClient = DummyAsyncClient
sys.modules['httpx'] = fake_httpx



# Patch pydantic field name restrictions
import pydantic.utils
import pydantic.main
pydantic.utils.validate_field_name = lambda bases, name: None
pydantic.main.validate_field_name = pydantic.utils.validate_field_name

# Patch redis modules to use FakeRedis
fake_asyncio = types.ModuleType('redis.asyncio')
fake_asyncio.Redis = FakeRedis
sys.modules['redis.asyncio'] = fake_asyncio
fake_exceptions = types.ModuleType('redis.exceptions')
fake_exceptions.RedisError = Exception
sys.modules['redis.exceptions'] = fake_exceptions
fake_root = types.ModuleType('redis')
fake_root.asyncio = fake_asyncio
fake_root.exceptions = fake_exceptions
fake_root.Redis = FakeRedis
sys.modules['redis'] = fake_root

# Reload modules that depend on redis
import shared.utils.redis_client as redis_client
importlib.reload(redis_client)
from shared.utils.redis_manager import RedisManager
from services.api.conversations import ConversationService
from services.api.router import (
    start_conversation,
    send_message,
    list_conversations,
    get_conversation,
    get_conversation_messages,
    list_agents,
    get_agent_status,
    health,
)
from services.api.models.conversation import StartConversationRequest, SendMessageRequest

class DummyAgentLifecycleClient:
    async def get_agent_status(self, agent_id):
        return {
            "agent_id": agent_id,
            "name": "Agent",
            "status": "active",
            "is_available": True,
            "active_conversations": 0,
            "last_active": datetime.now().isoformat()
        }

    async def list_agents(self, status=None, skip=0, limit=100):
        return {
            "agents": [{
                "agent_id": "agent1",
                "config": {"persona": {"name": "Agent", "description": "Test agent"}},
                "status": "active",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }],
            "total": 1
        }

class DummyAgentServiceClient:
    async def send_message(self, agent_id, user_id, message, conversation_id=None):
        return {"message": {
            "id": "m1",
            "role": "agent",
            "content": "ack",
            "timestamp": datetime.now().isoformat(),
            "metadata": {}
        }}

import pytest

@pytest.fixture
def service():
    manager = RedisManager(host='localhost', port=6379, db=0)
    asyncio.run(manager.connect())
    svc = ConversationService(
        redis_manager=manager,
        agent_service_client=DummyAgentServiceClient(),
        agent_lifecycle_client=DummyAgentLifecycleClient(),
    )
    asyncio.run(svc.initialize())
    return svc


def start_conv(service):
    req = StartConversationRequest(agent_id="agent1", user_id="user1", initial_message="hi")
    resp = asyncio.run(start_conversation(req, conversation_service=service))
    return resp.id


def test_start_conversation_endpoint(service):
    cid = start_conv(service)
    assert cid


def test_send_message_endpoint(service):
    cid = start_conv(service)
    req = SendMessageRequest(content="hello", user_id="user1")
    resp = asyncio.run(send_message(cid, request=req, conversation_service=service))
    assert resp.conversation_id == cid


def test_get_conversation_endpoint(service):
    cid = start_conv(service)
    resp = asyncio.run(get_conversation(cid, conversation_service=service))
    assert resp.id == cid


def test_get_conversation_messages_endpoint(service):
    cid = start_conv(service)
    req = SendMessageRequest(content="hi", user_id="user1")
    asyncio.run(send_message(cid, request=req, conversation_service=service))
    resp = asyncio.run(
        get_conversation_messages(
            cid,
            skip=0,
            limit=100,
            conversation_service=service,
        )
    )
    assert resp.conversation_id == cid
    assert resp.total >= 4


def test_list_conversations_endpoint(service):
    cid = start_conv(service)
    resp = asyncio.run(
        list_conversations(
            user_id="user1",
            agent_id=None,
            status=None,
            skip=0,
            limit=100,
            conversation_service=service,
        )
    )
    ids = [c.id for c in resp.conversations]
    assert cid in ids


def test_list_agents_endpoint(service):
    resp = asyncio.run(list_agents(agent_lifecycle_client=DummyAgentLifecycleClient()))
    assert resp.total == 1


def test_get_agent_status_endpoint(service):
    resp = asyncio.run(get_agent_status("agent1", agent_lifecycle_client=DummyAgentLifecycleClient()))
    assert resp.agent_id == "agent1"


def test_health_endpoint():
    resp = asyncio.run(health())
    assert resp["status"] == "ok"
