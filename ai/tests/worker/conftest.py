from collections.abc import AsyncIterator, Iterator

import pytest
from redis.asyncio import Redis
from testcontainers.community.redis import RedisContainer

# compose.yaml과 같은 이미지
REDIS_IMAGE = "redis:8"


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    """테스트용 Redis를 띄운 주소. Docker가 필요하다."""
    with RedisContainer(REDIS_IMAGE) as container:
        yield f"redis://{container.get_container_host_ip()}:{container.get_exposed_port(6379)}/0"


@pytest.fixture
async def redis(redis_url: str) -> AsyncIterator[Redis]:
    """테스트마다 비운 Redis."""
    client = Redis.from_url(redis_url, decode_responses=True)
    await client.flushdb()
    yield client
    await client.aclose()
