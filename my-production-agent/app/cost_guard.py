"""Redis-backed monthly LLM cost guard."""
import calendar
import time
from dataclasses import dataclass

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import get_redis


@dataclass(frozen=True)
class Usage:
    user_id: str
    month: str
    request_count: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    budget_usd: float

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.budget_usd - self.cost_usd)


class CostGuard:
    def __init__(self, budget_usd: float) -> None:
        self.budget_usd = budget_usd

    def _month(self) -> str:
        return time.strftime("%Y-%m")

    def _key(self, user_id: str) -> str:
        return f"cost:{self._month()}:{user_id}"

    def _seconds_until_next_month(self) -> int:
        now = time.localtime()
        _, days_in_month = calendar.monthrange(now.tm_year, now.tm_mon)
        end_of_month = time.mktime(
            (now.tm_year, now.tm_mon, days_in_month, 23, 59, 59, 0, 0, -1)
        )
        return max(3600, int(end_of_month - time.time()) + 86400)

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens / 1000 * settings.input_price_per_1k_tokens
            + output_tokens / 1000 * settings.output_price_per_1k_tokens
        )

    def get_usage(self, user_id: str) -> Usage:
        client = get_redis()
        data = client.hgetall(self._key(user_id))
        return Usage(
            user_id=user_id,
            month=self._month(),
            request_count=int(data.get("request_count", 0)),
            input_tokens=int(float(data.get("input_tokens", 0))),
            output_tokens=int(float(data.get("output_tokens", 0))),
            cost_usd=float(data.get("cost_usd", 0.0)),
            budget_usd=self.budget_usd,
        )

    def check_budget(self, user_id: str, projected_cost_usd: float = 0.0) -> Usage:
        try:
            usage = self.get_usage(user_id)
        except redis.RedisError as exc:
            raise HTTPException(status_code=503, detail="Cost guard storage unavailable") from exc

        if usage.cost_usd + projected_cost_usd > self.budget_usd:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "Monthly budget exceeded",
                    "used_usd": round(usage.cost_usd, 6),
                    "projected_usd": round(projected_cost_usd, 6),
                    "budget_usd": self.budget_usd,
                    "resets": "next calendar month",
                },
            )

        return usage

    def record_usage(self, user_id: str, input_tokens: int, output_tokens: int) -> Usage:
        cost = self.estimate_cost(input_tokens, output_tokens)
        key = self._key(user_id)
        client = get_redis()

        try:
            pipe = client.pipeline()
            pipe.hincrby(key, "request_count", 1)
            pipe.hincrby(key, "input_tokens", input_tokens)
            pipe.hincrby(key, "output_tokens", output_tokens)
            pipe.hincrbyfloat(key, "cost_usd", cost)
            pipe.expire(key, self._seconds_until_next_month())
            pipe.execute()
            return self.get_usage(user_id)
        except redis.RedisError as exc:
            raise HTTPException(status_code=503, detail="Cost guard storage unavailable") from exc


cost_guard = CostGuard(settings.monthly_budget_usd)
