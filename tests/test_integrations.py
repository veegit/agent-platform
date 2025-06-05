import sys
import types
import asyncio
import importlib
from tests.helpers import FakeRedis

# Stub httpx
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

# Stub serpapi
fake_serpapi = types.ModuleType('serpapi')
class DummyGoogleSearch:
    def __init__(self, params):
        self.params = params
    def get_dict(self):
        return {"organic_results": [{"title": "Test", "link": "http://x", "snippet": "ok", "displayed_link": "x"}]}
fake_serpapi.GoogleSearch = DummyGoogleSearch
sys.modules['serpapi'] = fake_serpapi

# Patch pydantic restriction
import pydantic.utils
import pydantic.main
pydantic.utils.validate_field_name = lambda bases, name: None
pydantic.main.validate_field_name = pydantic.utils.validate_field_name

# Setup fake redis modules
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

from services.agent_service import llm
from services.skill_service.skills import web_search

class MockResponse:
    def __init__(self, data):
        self.status_code = 200
        self._data = data
    def json(self):
        return self._data

def test_llm_call(monkeypatch):
    async def dummy_post(self, *a, **k):
        return MockResponse({"choices": [{"message": {"content": "hello"}}]})
    monkeypatch.setattr(llm.httpx.AsyncClient, "post", dummy_post)
    result = asyncio.run(llm.call_llm([{"role": "user", "content": "hi"}]))
    assert result["content"] == "hello"

def test_web_search(monkeypatch):
    result = asyncio.run(web_search.execute({"query": "python", "num_results": 1}))
    assert result["results"][0]["title"] == "Test"
