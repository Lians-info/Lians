from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from src.agentmem.db import Base
from src.agentmem.memory_service import add_memory, recall_memories
from src.agentmem.schemas import MemoryAdd, RecallRequest


@dataclass(frozen=True)
class Case:
    query: str
    as_of: datetime
    expected: str


async def main() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        pg_indexes = [
            idx
            for table in Base.metadata.tables.values()
            for idx in table.indexes
            if idx.dialect_kwargs.get("postgresql_using") is not None
        ]
        for idx in pg_indexes:
            idx.table.indexes.discard(idx)
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        ns = "bench"
        agent = "research"
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        t1 = datetime(2026, 5, 1, tzinfo=timezone.utc)

        await add_memory(
            db,
            ns,
            MemoryAdd(
                agent_id=agent,
                content="NVDA Q3 guidance $32B",
                event_time=t0,
                metadata={"ticker": "NVDA", "metric": "guidance"},
            ),
        )
        await add_memory(
            db,
            ns,
            MemoryAdd(
                agent_id=agent,
                content="NVDA Q3 guidance raised to $36B",
                event_time=t1,
                metadata={"ticker": "NVDA", "metric": "guidance"},
            ),
        )

        cases = [
            Case("NVDA guidance", datetime(2026, 2, 1, tzinfo=timezone.utc), "$32B"),
            Case("NVDA guidance", datetime(2026, 6, 1, tzinfo=timezone.utc), "$36B"),
        ]

        hits = 0
        for case in cases:
            result = await recall_memories(
                db,
                ns,
                RecallRequest(agent_id=agent, query=case.query, as_of=case.as_of, k=1),
            )
            top = result.memories[0].content if result.memories else ""
            ok = case.expected in (top or "")
            hits += int(ok)
            print(f"{case.as_of.date()} expected={case.expected} top={top!r} ok={ok}")

        print(f"point_in_time_accuracy={hits / len(cases):.2f}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
