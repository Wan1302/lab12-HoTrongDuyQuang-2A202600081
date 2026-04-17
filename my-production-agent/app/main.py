"""Production-ready AI agent for Day 12 lab."""
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import redis
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.auth import AuthContext, verify_api_key
from app.config import settings
from app.cost_guard import cost_guard
from app.rate_limiter import check_rate_limit
from app.redis_client import get_redis, ping_redis
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    extra_fields = {
        "client",
        "duration_ms",
        "event",
        "history_messages",
        "key_id",
        "method",
        "path",
        "session_id",
        "status_code",
        "user_id",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field_name in self.extra_fields:
            if hasattr(record, field_name):
                payload[field_name] = getattr(record, field_name)
        return json.dumps(payload)


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    handlers=[handler],
    force=True,
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
READY = False
REQUEST_COUNT = 0
ERROR_COUNT = 0


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str = Field("default-user", min_length=1, max_length=128)
    session_id: str | None = Field(default=None, max_length=128)


class AskResponse(BaseModel):
    session_id: str
    user_id: str
    question: str
    answer: str
    model: str
    turn: int
    served_by: str
    usage: dict[str, int | float]
    timestamp: str


def _history_key(user_id: str, session_id: str) -> str:
    return f"conversation:{user_id}:{session_id}"


def _append_history(user_id: str, session_id: str, role: str, content: str) -> None:
    client = get_redis()
    key = _history_key(user_id, session_id)
    entry = json.dumps(
        {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )

    try:
        pipe = client.pipeline()
        pipe.rpush(key, entry)
        pipe.ltrim(key, -settings.history_max_messages, -1)
        pipe.expire(key, settings.conversation_ttl_seconds)
        pipe.execute()
    except redis.RedisError as exc:
        raise HTTPException(status_code=503, detail="Conversation storage unavailable") from exc


def _load_history(user_id: str, session_id: str) -> list[dict[str, str]]:
    try:
        raw_messages = get_redis().lrange(_history_key(user_id, session_id), 0, -1)
    except redis.RedisError as exc:
        raise HTTPException(status_code=503, detail="Conversation storage unavailable") from exc

    messages: list[dict[str, str]] = []
    for raw_message in raw_messages:
        try:
            messages.append(json.loads(raw_message))
        except json.JSONDecodeError:
            logger.warning("Skipping invalid history entry", extra={"event": "history_decode_error"})
    return messages


def _estimate_tokens(text: str) -> int:
    return max(1, len(text.split()) * 2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global READY
    logger.info(
        "Starting application",
        extra={"event": "startup"},
    )

    READY = ping_redis()
    if not READY:
        logger.error("Redis is not reachable during startup", extra={"event": "startup_redis_failed"})

    yield

    # Uvicorn handles SIGTERM gracefully; this block flips readiness before exit.
    READY = False
    logger.info("Application shutting down after SIGTERM or server stop", extra={"event": "shutdown"})


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global REQUEST_COUNT, ERROR_COUNT
    start = time.time()
    REQUEST_COUNT += 1

    try:
        response: Response = await call_next(request)
    except Exception:
        ERROR_COUNT += 1
        logger.exception("Unhandled request error", extra={"event": "request_error"})
        raise

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"

    logger.info(
        "Request completed",
        extra={
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round((time.time() - start) * 1000, 2),
        },
    )
    return response


@app.get("/", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "instance_id": settings.instance_id,
    }


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
def ask_agent(
    body: AskRequest,
    request: Request,
    auth: AuthContext = Depends(verify_api_key),
):
    user_id = body.user_id.strip()
    session_id = body.session_id or str(uuid.uuid4())

    rate = check_rate_limit(user_id)
    input_tokens = _estimate_tokens(body.question)
    projected_cost = cost_guard.estimate_cost(input_tokens, 0)
    cost_guard.check_budget(user_id, projected_cost)

    _append_history(user_id, session_id, "user", body.question)
    history = _load_history(user_id, session_id)

    logger.info(
        "Calling LLM",
        extra={
            "event": "agent_call",
            "user_id": user_id,
            "session_id": session_id,
            "history_messages": len(history),
            "client": request.client.host if request.client else "unknown",
            "key_id": auth.key_id,
        },
    )

    answer = llm_ask(body.question)
    output_tokens = _estimate_tokens(answer)
    projected_cost = cost_guard.estimate_cost(input_tokens, output_tokens)
    cost_guard.check_budget(user_id, projected_cost)
    usage = cost_guard.record_usage(user_id, input_tokens, output_tokens)
    _append_history(user_id, session_id, "assistant", answer)

    turn = len([message for message in history if message.get("role") == "user"])
    return AskResponse(
        session_id=session_id,
        user_id=user_id,
        question=body.question,
        answer=answer,
        model=settings.llm_model,
        turn=turn,
        served_by=settings.instance_id,
        usage={
            "request_count": usage.request_count,
            "cost_usd": round(usage.cost_usd, 6),
            "budget_remaining_usd": round(usage.remaining_usd, 6),
            "rate_limit_remaining": rate["remaining"],
        },
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/history/{user_id}/{session_id}", tags=["Agent"])
def get_history(
    user_id: str,
    session_id: str,
    _: AuthContext = Depends(verify_api_key),
):
    return {
        "user_id": user_id,
        "session_id": session_id,
        "messages": _load_history(user_id, session_id),
    }


@app.get("/health", tags=["Operations"])
def health():
    redis_ok = ping_redis()
    return {
        "status": "ok",
        "version": settings.app_version,
        "environment": settings.environment,
        "instance_id": settings.instance_id,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": REQUEST_COUNT,
        "checks": {
            "redis": "ok" if redis_ok else "unavailable",
            "llm": "openai" if settings.openai_api_key else "mock",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    if not READY or not ping_redis():
        raise HTTPException(status_code=503, detail="Redis is not ready")
    return {
        "ready": True,
        "instance_id": settings.instance_id,
        "storage": "redis",
    }


@app.get("/metrics", tags=["Operations"])
def metrics(_: AuthContext = Depends(verify_api_key)):
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": REQUEST_COUNT,
        "error_count": ERROR_COUNT,
        "rate_limit_per_minute": settings.rate_limit_per_minute,
        "monthly_budget_usd": settings.monthly_budget_usd,
        "storage": "redis",
    }


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
