"""Shared Redis connection helpers."""
from functools import lru_cache

import redis

from app.config import settings


@lru_cache(maxsize=1)
def get_redis() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def ping_redis() -> bool:
    try:
        return bool(get_redis().ping())
    except (redis.RedisError, ValueError):
        return False
