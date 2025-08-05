import sys
import types
import asyncio
import importlib
from tests.helpers import FakeRedis

# Patch redis modules
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

from services.agent_lifecycle.repository import AgentRepository
from services.agent_lifecycle.models.agent import (
    Agent,
    AgentStatus,
    AgentConfig,
    AgentPersona,
    MemoryConfig,
)
from services.agent_lifecycle.models.agent import LLMConfig


def test_create_agent_registers_domain():
    manager = RedisManager(host='localhost', port=6379, db=0)
    asyncio.run(manager.connect())
    repo = AgentRepository(manager)
    asyncio.run(repo.initialize())

    config = AgentConfig(
        agent_id='finance-agent',
        persona=AgentPersona(
            name='Fin',
            description='Fin agent',
            goals=[],
            constraints=[],
            tone='neutral',
            system_prompt=''
        ),
        llm=LLMConfig(model_name='gemini-2.5-flash'),
        skills=['finance'],
        memory=MemoryConfig(),
        is_supervisor=False,
    )

    agent = Agent(agent_id='finance-agent', status=AgentStatus.INACTIVE, config=config)
    asyncio.run(repo.create_agent(agent, domain='finance', keywords=['stock']))

    mapping = asyncio.run(manager.delegation_store.get_domain('finance'))
    assert mapping['agent_id'] == 'finance-agent'
    assert 'stock' in mapping['keywords']
