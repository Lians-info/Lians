from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Memory, EventLog
from ..schemas import EraseRequest, EraseResult
from ..pii import destroy_subject_key
from .deps import get_auth, AuthContext

router = APIRouter(prefix="/v1", tags=["privacy"])


@router.post("/erase", response_model=EraseResult)
async def erase_subject(
    req: EraseRequest,
    auth: AuthContext = Depends(get_auth),
    db: AsyncSession = Depends(get_db),
):
    auth.require("admin")

    # Find all memories for this subject in this namespace
    stmt = select(Memory).where(
        and_(
            Memory.namespace == auth.namespace,
            Memory.subject_id == req.subject_id,
            Memory.erased_at.is_(None),
        )
    )
    result = await db.execute(stmt)
    memories = result.scalars().all()

    now = datetime.now(timezone.utc)
    count = 0
    for mem in memories:
        mem.content_encrypted = None
        mem.erased_at = now
        db.add(EventLog(
            namespace=auth.namespace,
            agent_id=mem.agent_id,
            op="erase",
            memory_id=mem.id,
            content_hash=mem.content_hash,
            payload={
                "subject_id": req.subject_id,
                "request_ref": req.request_ref,
            },
        ))
        count += 1

    # Crypto-shred the subject key
    await destroy_subject_key(db, req.subject_id)

    await db.commit()

    return EraseResult(
        subject_id=req.subject_id,
        memories_erased=count,
        request_ref=req.request_ref,
    )
