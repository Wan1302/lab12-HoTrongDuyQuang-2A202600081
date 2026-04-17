"""Redis-backed sliding-window rate limiter."""
import time
import uuid

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import get_redis


def check_rate_limit(user_id: str) -> dict[str, int]:
    client = get_redis()
    now = time.time()
    window_start = now - settings.rate_limit_window_seconds
    key = f"rate:{user_id}"

    try:
        pipe = client.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        _, request_count = pipe.execute()

        if request_count >= settings.rate_limit_per_minute:
            oldest = client.zrange(key, 0, 0, withscores=True)
            retry_after = settings.rate_limit_window_seconds
            if oldest:
                retry_after = max(1, int(oldest[0][1] + settings.rate_limit_window_seconds - now))

            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "limit": settings.rate_limit_per_minute,
                    "window_seconds": settings.rate_limit_window_seconds,
                    "retry_after_seconds": retry_after,
                },
                headers={
                    "X-RateLimit-Limit": str(settings.rate_limit_per_minute),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": str(retry_after),
                },
            )

        member = f"{now}:{uuid.uuid4().hex}"
        pipe = client.pipeline()
        pipe.zadd(key, {member: now})
        pipe.expire(key, settings.rate_limit_window_seconds * 2)
        pipe.execute()

        remaining = settings.rate_limit_per_minute - request_count - 1
        return {
            "limit": settings.rate_limit_per_minute,
            "remaining": max(0, remaining),
            "reset_seconds": settings.rate_limit_window_seconds,
        }
    except redis.RedisError as exc:
        raise HTTPException(status_code=503, detail="Rate limiter storage unavailable") from exc
