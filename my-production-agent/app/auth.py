"""API key authentication for protected endpoints."""
from dataclasses import dataclass
from secrets import compare_digest

from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

from app.config import settings


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    key_id: str


def verify_api_key(api_key: str | None = Security(api_key_header)) -> AuthContext:
    if not api_key or not compare_digest(api_key, settings.agent_api_key):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Include header X-API-Key.",
        )

    return AuthContext(key_id=api_key[:8])
