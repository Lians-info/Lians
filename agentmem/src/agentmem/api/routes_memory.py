from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..schemas import MemoryAdd, MemoryOut, RecallRequest, RecallResult
from ..memory_service import add_memory, recall_memories
from .deps import get_auth, AuthContext

router = APIRouter(prefix="/v1", tags=["memory"])


@router.post("/memories", response_model=MemoryOut)
async def create_memory(
    req: MemoryAdd,
    auth: AuthContext = Depends(get_auth),
    db: AsyncSession = Depends(get_db),
):
    auth.require("write")
    return await add_memory(db, auth.namespace, req)


@router.post("/recall", response_model=RecallResult)
async def recall(
    req: RecallRequest,
    auth: AuthContext = Depends(get_auth),
    db: AsyncSession = Depends(get_db),
):
    auth.require("read")
    return await recall_memories(db, auth.namespace, req)
