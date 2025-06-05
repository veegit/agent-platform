import sys
import types
import asyncio
import importlib
from tests.helpers import FakeRedis

# Reuse patches from integration test
fake_httpx = types.ModuleType('httpx')
class DummyAsyncClient:
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc, tb):
        pass
    async def post(self, *a, **k):
        return MockResponse({"choices": [{"message": {"content": "stub"}}]})
fake_httpx.AsyncClient = DummyAsyncClient
sys.modules['httpx'] = fake_httpx

fake_serpapi = types.ModuleType('serpapi')
class DummyGoogleSearch:
    def __init__(self, params):
        self.params = params
    def get_dict(self):
        return {"organic_results": [{"title": "Test", "link": "http://x", "snippet": "ok", "displayed_link": "x"}]}
fake_serpapi.GoogleSearch = DummyGoogleSearch
sys.modules['serpapi'] = fake_serpapi

import pydantic.utils, pydantic.main
pydantic.utils.validate_field_name = lambda bases, name: None
pydantic.main.validate_field_name = pydantic.utils.validate_field_name

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

import shared.utils.redis_client as redis_client
importlib.reload(redis_client)
from shared.utils.redis_manager import RedisManager
from services.api.conversations import ConversationService
from services.skill_service.skills import web_search

class MockResponse:
    def __init__(self, data):
        self.status_code = 200
        self._data = data
    def json(self):
        return self._data

class DummyAgentLifecycleClient:
    async def get_agent_status(self, agent_id):
        return {"agent_id": agent_id, "is_available": True}

class DummyAgentServiceClient:
    async def send_message(self, agent_id, user_id, message, conversation_id=None):
        if "search" in message.lower():
            result = await web_search.execute({"query": message, "num_results": 1})
            return {"message": {"role": "assistant", "content": str(result)}}
        return {"message": {"role": "assistant", "content": "ack"}}

def test_smoke_conversation():
    manager = RedisManager(host='localhost', port=6379, db=0)
    asyncio.run(manager.connect())
    service = ConversationService(
        redis_manager=manager,
        agent_service_client=DummyAgentServiceClient(),
        agent_lifecycle_client=DummyAgentLifecycleClient()
    )
    asyncio.run(service.initialize())

    conv = asyncio.run(service.start_conversation(
        agent_id='agent1',
        user_id='user1',
        initial_message='hello',
        metadata={"title": "Test"}
    ))
    conv_id = conv['id']
    asyncio.run(service.send_message(conv_id, 'search for python', 'user1'))
    data = asyncio.run(service.get_conversation(conv_id))
    assert len(data['messages']) == 4
    assert 'Test' in data['messages'][-1]['content']
