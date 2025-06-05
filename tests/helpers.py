class FakeRedis:
    def __init__(self, *args, **kwargs):
        self.store = {}
    async def ping(self):
        return True
    async def setex(self, key, expiry, value):
        self.store[key] = value
        return True
    async def set(self, key, value):
        self.store[key] = value
        return True
    async def get(self, key):
        return self.store.get(key)
    async def delete(self, key):
        return 1 if self.store.pop(key, None) is not None else 0
    async def exists(self, key):
        return 1 if key in self.store else 0
    async def rpush(self, key, value):
        self.store.setdefault(key, []).append(value)
        return len(self.store[key])
    async def lrange(self, key, start, end):
        lst = self.store.get(key, [])
        if end == -1:
            end = None
        else:
            end += 1
        return lst[start:end]
    async def hset(self, key, mapping=None, **kwargs):
        self.store.setdefault(key, {})
        if mapping:
            self.store[key].update(mapping)
        self.store[key].update(kwargs)
        return True
    async def hgetall(self, key):
        return self.store.get(key, {})
    async def hget(self, key, field):
        return self.store.get(key, {}).get(field)
    async def sadd(self, key, *values):
        s = self.store.setdefault(key, set())
        before = len(s)
        for v in values:
            s.add(v)
        return len(s) - before
    async def smembers(self, key):
        return self.store.get(key, set())
    async def srem(self, key, *values):
        s = self.store.setdefault(key, set())
        removed = 0
        for v in values:
            if v in s:
                s.remove(v)
                removed += 1
        return removed
    async def close(self):
        pass
