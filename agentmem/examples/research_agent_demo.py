"""
Demo: research agent that tracks earnings revisions using AgentMem.

Shows the core value prop: point-in-time recall for compliance/audit.
Run against a local server: uvicorn src.agentmem.main:app --reload
"""
import asyncio
from datetime import datetime, timezone

from sdk.python.agentmem_sdk.client import AgentMemClient


async def main():
    client = AgentMemClient(base_url="http://localhost:8000", api_key="your-api-key")
    agent = "research-agent-1"

    print("--- Adding earnings guidance sequence ---")
    await client.add(
        agent_id=agent,
        content="NVDA Q3 FY2026 guidance: $32B",
        event_time=datetime(2026, 2, 1, tzinfo=timezone.utc),
        source="earnings_call",
        metadata={"ticker": "NVDA", "metric": "guidance", "quarter": "Q3FY26"},
    )
    print("Added: Q3 guidance $32B")

    await client.add(
        agent_id=agent,
        content="NVDA raises Q3 FY2026 guidance to $36B (analyst day)",
        event_time=datetime(2026, 5, 10, tzinfo=timezone.utc),
        source="analyst_day",
        metadata={"ticker": "NVDA", "metric": "guidance", "quarter": "Q3FY26"},
    )
    print("Added: Q3 guidance raised to $36B")

    print("\n--- Present-time recall ---")
    result = await client.recall(agent_id=agent, query="NVDA Q3 guidance", k=3)
    for mem in result["memories"]:
        print(f"  [{mem['event_time'][:10]}] {mem['content']} (valid_to={mem['valid_to']})")

    print("\n--- Point-in-time recall (as of Feb 2026 — before the revision) ---")
    past_result = await client.recall(
        agent_id=agent,
        query="NVDA Q3 guidance",
        k=3,
        as_of=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )
    for mem in past_result["memories"]:
        print(f"  [{mem['event_time'][:10]}] {mem['content']}")

    print("\n--- Audit reconstruction ---")
    audit = await client.reconstruct(
        agent_id=agent,
        as_of=datetime(2026, 3, 1, tzinfo=timezone.utc),
        query="NVDA guidance",
    )
    print(f"  Memories at that time: {len(audit['memories'])}")
    print(f"  Event log entries: {len(audit['event_trail'])}")


if __name__ == "__main__":
    asyncio.run(main())
