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

# Stub httpx for finance skill
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
    async def get(self, url, params=None, timeout=None):
        # Return fake Alpha Vantage quote
        if 'alphavantage' in url:
            return DummyResponse({
                'Global Quote': {
                    '05. price': '150.00',
                    '07. latest trading day': '2025-06-10'
                }
            })
        return DummyResponse({})
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

# Patch pydantic field restrictions
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

# Reload redis client to use FakeRedis
import shared.utils.redis_client as redis_client
importlib.reload(redis_client)
from shared.utils.redis_manager import RedisManager

from services.agent_service.memory import MemoryManager
from services.agent_service.agent import Agent
import services.agent_service.agent as agent_module
from services.agent_service.models.config import AgentConfig, AgentPersona, MemoryConfig, ReasoningModel
from services.agent_service.models.state import AgentState, Message, MessageRole, AgentOutput


class DummyGraph:
    async def ainvoke(self, state_dict):
        state = AgentState(**state_dict)
        state.messages.append(Message(
            id='ack', role=MessageRole.AGENT, content='ack', timestamp=datetime.now()
        ))
        return state.dict()
    async def invoke(self, state_dict):
        return await self.ainvoke(state_dict)

def test_supervisor_finance_delegation():
    agent_module.create_agent_graph = lambda config, skill_client=None: DummyGraph()

    manager = RedisManager(host='localhost', port=6379, db=0)
    asyncio.run(manager.connect())
    mem = MemoryManager(manager)
    asyncio.run(mem.initialize())

    finance_config = AgentConfig(
        agent_id='finance-agent',
        persona=AgentPersona(
            name='Finance',
            description='Finance agent',
            goals=[],
            constraints=[],
            tone='neutral',
            system_prompt=''
        ),
        reasoning_model=ReasoningModel.LLAMA3_70B,
        skills=['finance'],
        memory=MemoryConfig(),
        is_supervisor=False
    )

    finance_agent = Agent(finance_config, memory_manager=mem)

    async def dummy_finance(msg, user_id, conversation_id=None):
        message = Message(id='f1', role=MessageRole.AGENT, content='AAPL price is $150', timestamp=datetime.now())
        state = AgentState(agent_id='finance-agent', conversation_id=conversation_id or 'c1', user_id=user_id, messages=[message])
        return AgentOutput(message=message, state=state)

    finance_agent.process_message = dummy_finance

    supervisor_config = AgentConfig(
        agent_id='supervisor-agent',
        persona=AgentPersona(
            name='Supervisor',
            description='Coordinator',
            goals=[],
            constraints=[],
            tone='helpful',
            system_prompt=''
        ),
        reasoning_model=ReasoningModel.LLAMA3_70B,
        skills=[],
        memory=MemoryConfig(),
        is_supervisor=True
    )

    supervisor = Agent(
        supervisor_config,
        memory_manager=mem,
        delegations={'finance': {'agent': finance_agent, 'keywords': ['stock', 'share', 'ticker']}}
    )
    asyncio.run(supervisor.initialize())

    out = asyncio.run(supervisor.process_message('What is the current price of AAPL stock?', 'user1'))
    assert 'AAPL' in out.message.content

    out2 = asyncio.run(supervisor.process_message('hello there', 'user1'))
    assert out2.message.content == 'ack'


def test_supervisor_general_delegation():
    agent_module.create_agent_graph = lambda config, skill_client=None: DummyGraph()

    manager = RedisManager(host='localhost', port=6379, db=0)
    asyncio.run(manager.connect())
    mem = MemoryManager(manager)
    asyncio.run(mem.initialize())

    demo_config = AgentConfig(
        agent_id='demo-agent',
        persona=AgentPersona(
            name='Demo',
            description='General agent',
            goals=[],
            constraints=[],
            tone='neutral',
            system_prompt=''
        ),
        reasoning_model=ReasoningModel.LLAMA3_70B,
        skills=['web-search'],
        memory=MemoryConfig(),
        is_supervisor=False
    )

    demo_agent = Agent(demo_config, memory_manager=mem)

    async def dummy_demo(msg, user_id, conversation_id=None):
        message = Message(id='d1', role=MessageRole.AGENT, content='demo response', timestamp=datetime.now())
        state = AgentState(agent_id='demo-agent', conversation_id=conversation_id or 'c1', user_id=user_id, messages=[message])
        return AgentOutput(message=message, state=state)

    demo_agent.process_message = dummy_demo

    supervisor_config = AgentConfig(
        agent_id='supervisor-agent',
        persona=AgentPersona(name='Sup', description='sup', goals=[], constraints=[], tone='helpful', system_prompt=''),
        reasoning_model=ReasoningModel.LLAMA3_70B,
        skills=[],
        memory=MemoryConfig(),
        is_supervisor=True
    )

    supervisor = Agent(
        supervisor_config,
        memory_manager=mem,
        delegations={'general': {'agent': demo_agent, 'keywords': ['search']}}
    )
    asyncio.run(supervisor.initialize())

    out = asyncio.run(supervisor.process_message('search the web', 'u1'))
    assert out.message.content == 'demo response'
