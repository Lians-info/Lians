"""
FastAPI dependencies: API key auth, namespace resolution, DB session.
"""
from __future__ import annotations
import hashlib
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import ApiKey

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class AuthContext:
    def __init__(self, namespace: str, scopes: list[str]):
        self.namespace = namespace
        self.scopes = scopes

    def require(self, scope: str):
        if scope not in self.scopes:
            raise HTTPException(status_code=403, detail=f"Scope '{scope}' required")


async def get_auth(
    raw_key: Annotated[Optional[str], Security(_api_key_header)],
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    if not raw_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    hashed = _hash_key(raw_key)
    stmt = select(ApiKey).where(
        and_(
            ApiKey.hashed_key == hashed,
            ApiKey.revoked_at.is_(None),
        )
    )
    result = await db.execute(stmt)
    key_row = result.scalar_one_or_none()

    if key_row is None:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")

    return AuthContext(
        namespace=key_row.namespace,
        scopes=list(key_row.scopes or []),
    )
