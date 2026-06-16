"""
Supersession engine — decides what a new memory supersedes.

Phase 1: Stage 1 (candidate generation) + Stage 2 (rule-based classification).
Phase 2 adds: Stage 3 (LLM adjudication) for ambiguous pairs.

Relations:
  SUPERSEDES           — same entity+attribute, newer event_time, values differ
  CONFIRMS             — same entity+attribute, same value
  ADDS                 — related topic, distinct attribute
  CONTRADICTS_SAME_TIME — conflicting values, no clear temporal ordering
"""
from __future__ import annotations
import math
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Memory
from .schemas import SupersessionResult
from .crypto import decrypt_content


# Threshold: cosine similarity above this is considered "same topic"
_SIM_THRESHOLD = 0.82

# Keys that, when matching between old and new memory, lock in same entity+attribute
_STRUCTURED_KEYS = {"ticker", "metric", "entity", "instrument", "cusip", "isin", "field"}


def _metadata_overlap(old_meta: dict, new_meta: dict) -> set[str]:
    """Shared structured keys whose values also match."""
    shared = set(old_meta.keys()) & set(new_meta.keys()) & _STRUCTURED_KEYS
    return {k for k in shared if old_meta[k] == new_meta[k]}


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb + 1e-9)


async def find_supersession_candidates(
    db: AsyncSession,
    namespace: str,
    agent_id: str,
    new_meta: dict[str, Any],
    new_embedding: list[float],
    new_event_time: datetime,
) -> list[Memory]:
    """
    Stage 1: Find prior valid memories that share structured metadata keys
    AND have embedding similarity above threshold.
    """
    # Start with currently valid memories for this agent
    stmt = select(Memory).where(
        and_(
            Memory.namespace == namespace,
            Memory.agent_id == agent_id,
            Memory.valid_to.is_(None),
            Memory.erased_at.is_(None),
        )
    )
    result = await db.execute(stmt)
    candidates = result.scalars().all()

    filtered = []
    for mem in candidates:
        if not new_meta or mem.metadata_ is None:
            continue
        old_meta = dict(mem.metadata_)
        overlap = _metadata_overlap(old_meta, new_meta)
        if not overlap:
            continue

        # Full structured key match (e.g. same ticker + same metric) → definitive candidate
        new_structured = {k: new_meta[k] for k in new_meta if k in _STRUCTURED_KEYS}
        old_structured = {k: old_meta[k] for k in old_meta if k in _STRUCTURED_KEYS}
        full_match = new_structured and new_structured == old_structured

        if full_match:
            filtered.append(mem)
            continue

        # Partial match — require semantic similarity to confirm same topic
        if mem.embedding is None:
            continue
        emb = mem.embedding if isinstance(mem.embedding, list) else list(mem.embedding)
        sim = _cosine(emb, new_embedding)
        if sim >= _SIM_THRESHOLD:
            filtered.append(mem)

    return filtered


def classify_relation(
    old_content: Optional[str],
    new_content: str,
    old_event_time: datetime,
    new_event_time: datetime,
    old_meta: dict,
    new_meta: dict,
) -> tuple[str, float]:
    """
    Stage 2: Rule-based relation classification.
    Returns (relation, confidence).
    """
    old_metric = old_meta.get("metric") or old_meta.get("field")
    new_metric = new_meta.get("metric") or new_meta.get("field")
    if old_metric and new_metric and old_metric != new_metric:
        return "ADDS", 0.9

    # Normalize for simple equality check
    def _norm(s: Optional[str]) -> str:
        return (s or "").strip().lower()

    same_value = _norm(old_content) == _norm(new_content)

    # Normalise to UTC — SQLite returns naive datetimes
    from datetime import timezone as _tz
    def _utc(dt: datetime) -> datetime:
        return dt if dt.tzinfo else dt.replace(tzinfo=_tz.utc)

    old_event_time = _utc(old_event_time)
    new_event_time = _utc(new_event_time)

    # Temporal ordering
    if old_event_time < new_event_time:
        temporal_order = "new_is_later"
    elif old_event_time > new_event_time:
        temporal_order = "old_is_later"
    else:
        temporal_order = "same_time"

    if same_value:
        return "CONFIRMS", 0.9

    if temporal_order == "new_is_later":
        return "SUPERSEDES", 0.85

    if temporal_order == "same_time":
        # Different values at same event time — contradiction, keep both
        return "CONTRADICTS_SAME_TIME", 0.7

    # old_is_later — the "new" memory is actually older; don't supersede
    return "ADDS", 0.6


async def run_supersession(
    db: AsyncSession,
    namespace: str,
    agent_id: str,
    new_content: str,
    new_meta: dict[str, Any],
    new_embedding: list[float],
    new_event_time: datetime,
    subject_key: Optional[bytes] = None,
) -> SupersessionResult:
    """
    Full supersession funnel (Stage 1+2).
    Returns a SupersessionResult describing what to do.
    """
    candidates = await find_supersession_candidates(
        db, namespace, agent_id, new_meta, new_embedding, new_event_time
    )

    if not candidates:
        return SupersessionResult(relation="ADDS", confidence=1.0)

    superseded_ids: list[UUID] = []
    best_relation = "ADDS"
    best_confidence = 1.0

    for candidate in candidates:
        # Decrypt old content for comparison if we have the key
        old_content: Optional[str] = None
        if subject_key and candidate.content_encrypted:
            try:
                old_content = decrypt_content(bytes(candidate.content_encrypted), subject_key)
            except Exception:
                old_content = None

        relation, confidence = classify_relation(
            old_content=old_content,
            new_content=new_content,
            old_event_time=candidate.event_time,
            new_event_time=new_event_time,
            old_meta=dict(candidate.metadata_ or {}),
            new_meta=new_meta,
        )

        if relation == "SUPERSEDES":
            superseded_ids.append(candidate.id)
            best_relation = "SUPERSEDES"
            best_confidence = confidence
        elif relation == "CONTRADICTS_SAME_TIME" and best_relation != "SUPERSEDES":
            best_relation = "CONTRADICTS_SAME_TIME"
            best_confidence = confidence

    return SupersessionResult(
        relation=best_relation,
        confidence=best_confidence,
        superseded_ids=superseded_ids,
    )
