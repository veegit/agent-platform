import sys
import types
import asyncio
import importlib
from datetime import datetime

from tests.helpers import FakeRedis

# Stub langgraph to avoid dependency
fake_lg = types.ModuleType('langgraph.graph')
class DummyStateGraph:
    def add_node(self, *a, **k):
        pass
    def set_entry_point(self, *a, **k):
        pass
    def add_edge(self, *a, **k):
        pass
    def add_conditional_edges(self, *a, **k):
        pass
    def compile(self):
        class G:
            async def ainvoke(self, state):
                return state
            def invoke(self, state):
                return state
        return G()
fake_lg.StateGraph = lambda *a, **k: DummyStateGraph()
fake_lg.END = 'END'
sys.modules['langgraph.graph'] = fake_lg

# Minimal httpx stub
fake_httpx = types.ModuleType('httpx')
class DummyResponse:
    def __init__(self, data, status_code=200):
        self.status_code = status_code
        self._data = data
    def json(self):
        return self._data
class DummyAsyncClient:
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc, tb):
        pass
    async def post(self, *a, **k):
        return DummyResponse({})
fake_httpx.AsyncClient = DummyAsyncClient
sys.modules['httpx'] = fake_httpx

# Stub serpapi
fake_serpapi = types.ModuleType('serpapi')
class DummyGoogleSearch:
    def __init__(self, params):
        self.params = params
    def get_dict(self):
        return {'organic_results': []}
fake_serpapi.GoogleSearch = DummyGoogleSearch
sys.modules['serpapi'] = fake_serpapi

# Patch pydantic restrictions
import pydantic.utils
import pydantic.main
pydantic.utils.validate_field_name = lambda bases, name: None
pydantic.main.validate_field_name = pydantic.utils.validate_field_name

# Stub redis modules with FakeRedis
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

# Reload redis client
import shared.utils.redis_client as redis_client
importlib.reload(redis_client)
from shared.utils.redis_manager import RedisManager

from services.agent_service.memory import MemoryManager
from services.agent_service.agent import Agent
import services.agent_service.agent as agent_module
from services.agent_service.models.config import AgentConfig, AgentPersona, MemoryConfig, ReasoningModel
from services.agent_service.models.state import AgentState, Message, MessageRole


class DummyGraph:
    async def ainvoke(self, state_dict):
        state = AgentState(**state_dict)
        state.messages.append(
            Message(id='ack', role=MessageRole.AGENT, content='ack', timestamp=datetime.now())
        )
        return state.dict()
    async def invoke(self, state_dict):
        return await self.ainvoke(state_dict)


def test_single_agent_process_message():
    agent_module.create_agent_graph = lambda config, skill_client=None: DummyGraph()

    manager = RedisManager(host='localhost', port=6379, db=0)
    asyncio.run(manager.connect())
    mem = MemoryManager(manager)
    asyncio.run(mem.initialize())

    config = AgentConfig(
        agent_id='test-agent',
        persona=AgentPersona(
            name='Test',
            description='Single agent',
            goals=[],
            constraints=[],
            tone='neutral',
            system_prompt=''
        ),
        reasoning_model=ReasoningModel.LLAMA3_70B,
        skills=[],
        memory=MemoryConfig(),
        is_supervisor=False
    )

    agent = Agent(config, memory_manager=mem)
    asyncio.run(agent.initialize())

    out = asyncio.run(agent.process_message('hello', 'u1'))
    assert out.message.content == 'ack'

    out2 = asyncio.run(agent.process_message('another question', 'u1'))
    assert out2.message.content == 'ack'

