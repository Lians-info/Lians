from fastapi import FastAPI
from contextlib import asynccontextmanager

from .db import engine
from .models import Base
from .api.routes_memory import router as memory_router
from .api.routes_audit import router as audit_router
from .api.routes_privacy import router as privacy_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # In production use Alembic; this is dev-only auto-create
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="AgentMem",
    description="Financial-agent memory layer — bitemporal, auditable, erasable",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(memory_router)
app.include_router(audit_router)
app.include_router(privacy_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
