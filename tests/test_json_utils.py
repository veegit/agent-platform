import sys
import types
from datetime import datetime

# Provide fake redis modules before importing shared.utils
fake_asyncio = types.ModuleType('redis.asyncio')
fake_asyncio.Redis = lambda *a, **k: None
sys.modules['redis.asyncio'] = fake_asyncio
fake_exceptions = types.ModuleType('redis.exceptions')
fake_exceptions.RedisError = Exception
sys.modules['redis.exceptions'] = fake_exceptions
fake_root = types.ModuleType('redis')
fake_root.asyncio = fake_asyncio
fake_root.exceptions = fake_exceptions
fake_root.Redis = lambda *a, **k: None
sys.modules['redis'] = fake_root

from shared.utils.json_utils import dumps, loads

def test_datetime_serialization():
    data = {'time': datetime(2024, 1, 1, 12, 0, 0)}
    s = dumps(data)
    restored = loads(s)
    assert restored['time'] == '2024-01-01T12:00:00'
