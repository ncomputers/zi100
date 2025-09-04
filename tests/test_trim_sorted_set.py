import asyncio


from utils.redis import trim_sorted_set, trim_sorted_set_async


class DummyAsyncRedis:
    def __init__(self):
        self.args = None

    async def zremrangebyscore(self, key, min_score, max_score):
        self.args = (key, min_score, max_score)
        return 1


class DummySyncRedis:
    def __init__(self):
        self.args = None

    def zremrangebyscore(self, key, min_score, max_score):
        self.args = (key, min_score, max_score)
        return 1


def test_trim_sorted_set_sync_path():
    client = DummySyncRedis()
    trim_sorted_set(client, "k", 100, retention_secs=10)
    assert client.args == ("k", 0, 90)


def test_trim_sorted_set_async_path():
    client = DummyAsyncRedis()
    asyncio.run(trim_sorted_set_async(client, "k", 100, retention_secs=10))
    assert client.args == ("k", 0, 90)


def test_trim_sorted_set_sync_in_loop_no_error():
    client = DummyAsyncRedis()

    async def run():
        await asyncio.to_thread(trim_sorted_set, client, "k", 100, retention_secs=10)

    asyncio.run(run())
    assert client.args == ("k", 0, 90)
