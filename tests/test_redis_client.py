import sys
import types
import asyncio
import importlib
import pytest
from tests.helpers import FakeRedis

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
RedisClient = redis_client.RedisClient

@pytest.fixture
def client():
    return RedisClient(host='localhost', port=6379, db=0)

def test_set_get_value(client):
    asyncio.run(client.set_value('foo', {'bar': 1}))
    value = asyncio.run(client.get_value('foo'))
    assert value == {'bar': 1}

def test_list_operations(client):
    asyncio.run(client.add_to_list('mylist', 'a'))
    asyncio.run(client.add_to_list('mylist', 'b'))
    values = asyncio.run(client.get_list('mylist'))
    assert values == ['a', 'b']

def test_hash_operations(client):
    asyncio.run(client.set_hash('h', {'a': 1}))
    result = asyncio.run(client.get_hash('h'))
    assert result == {'a': 1}
