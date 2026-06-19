"""
AgentMem MCP (Model Context Protocol) server.

Exposes remember / recall / recall_at / reconstruct as native MCP tools so
any MCP-compatible in-house LLM can call AgentMem without a custom SDK adapter.
This is the integration path for financial firms running self-hosted models via
LiteLLM, vLLM, or similar — configure once in the model server, no per-agent
SDK code required.

Install:
    pip install mcp httpx

Run (stdio transport — standard for local LLM integration):
    python -m agentmem.mcp_server

Environment variables:
    AGENTMEM_URL        AgentMem API base URL (default: http://localhost:8000)
    AGENTMEM_API_KEY    API key with read+write scopes
    AGENTMEM_AGENT_ID   Agent identifier (default: mcp-agent)

Configure in your LLM server or Claude Desktop:
    {
      "mcpServers": {
        "agentmem": {
          "command": "python",
          "args": ["-m", "agentmem.mcp_server"],
          "env": {
            "AGENTMEM_URL": "https://your-agentmem.internal",
            "AGENTMEM_API_KEY": "agentmem_...",
            "AGENTMEM_AGENT_ID": "trading-desk-1"
          }
        }
      }
    }

The recall_at tool is the key differentiator over generic memory stores:
it returns the exact fact set that was valid at a past timestamp, enabling
true compliance reconstruction ("what did the model know before the trade?").
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

AGENTMEM_URL = os.environ.get("AGENTMEM_URL", "http://localhost:8000")
AGENTMEM_API_KEY = os.environ.get("AGENTMEM_API_KEY", "")
AGENTMEM_AGENT_ID = os.environ.get("AGENTMEM_AGENT_ID", "mcp-agent")


async def _api(method: str, path: str, body: dict | None = None) -> dict:
    import httpx
    headers = {"X-API-Key": AGENTMEM_API_KEY, "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        if method == "POST":
            r = await client.post(f"{AGENTMEM_URL}{path}", json=body, headers=headers)
        else:
            r = await client.get(f"{AGENTMEM_URL}{path}", params=body or {}, headers=headers)
        r.raise_for_status()
        return r.json()


def _fmt_memories(memories: list[dict]) -> str:
    if not memories:
        return "No relevant memories found."
    return "\n".join(
        f"[{(m.get('event_time') or '')[:10]}] {m.get('content') or '[erased]'}"
        for m in memories
    )


def _build_server() -> Any:
    from mcp.server import Server
    from mcp.types import Tool, TextContent

    server = Server("agentmem")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="remember",
                description=(
                    "Store a financial fact, observation, or decision in persistent memory. "
                    "Always provide event_time_iso as when the event occurred, not now. "
                    "Add ticker/metric/entity metadata for precise supersession detection — "
                    "this is what lets AgentMem automatically replace stale guidance numbers."
                ),
                inputSchema={
                    "type": "object",
                    "required": ["content", "event_time_iso"],
                    "properties": {
                        "content": {"type": "string"},
                        "event_time_iso": {
                            "type": "string",
                            "description": "ISO 8601 timestamp of when this event occurred.",
                        },
                        "metadata": {
                            "type": "object",
                            "description": "Tags: ticker, metric, entity, instrument, cusip, isin.",
                        },
                        "source": {
                            "type": "string",
                            "description": "Provenance: earnings_call, analyst_report, bloomberg, etc.",
                        },
                    },
                },
            ),
            Tool(
                name="recall",
                description=(
                    "Retrieve the most relevant CURRENT memories for a query. "
                    "Returns only presently-valid facts — superseded facts are excluded. "
                    "Call this before answering any question that may be in memory. "
                    "Use filters={ticker: NVDA} to narrow to a specific instrument."
                ),
                inputSchema={
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string"},
                        "k": {"type": "integer", "default": 5},
                        "filters": {
                            "type": "object",
                            "description": "Metadata equality filters, e.g. {ticker: NVDA}",
                        },
                    },
                },
            ),
            Tool(
                name="recall_at",
                description=(
                    "Retrieve memories that were valid at a specific past point in time. "
                    "Use for compliance and audit: 'What guidance did we have on 2026-03-01?' "
                    "Later superseding updates are excluded — this is true point-in-time recall. "
                    "Neither mem0 nor Zep support this; it is the core compliance differentiator."
                ),
                inputSchema={
                    "type": "object",
                    "required": ["query", "as_of_iso"],
                    "properties": {
                        "query": {"type": "string"},
                        "as_of_iso": {
                            "type": "string",
                            "description": "ISO 8601 timestamp for the point-in-time snapshot.",
                        },
                        "k": {"type": "integer", "default": 5},
                    },
                },
            ),
            Tool(
                name="reconstruct",
                description=(
                    "Reconstruct the complete memory state and full audit event trail "
                    "at a past point in time. Returns every memory that was valid at as_of "
                    "plus the timestamped, hashed event log behind them. "
                    "Use for regulatory audit submissions and trade reconstruction."
                ),
                inputSchema={
                    "type": "object",
                    "required": ["as_of_iso"],
                    "properties": {
                        "as_of_iso": {"type": "string"},
                        "query": {
                            "type": "string",
                            "description": "Optional semantic filter to narrow the memory set.",
                        },
                    },
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        try:
            if name == "remember":
                body = {
                    "agent_id": AGENTMEM_AGENT_ID,
                    "content": arguments["content"],
                    "event_time": arguments["event_time_iso"],
                    "source": arguments.get("source", "mcp"),
                    "metadata": arguments.get("metadata", {}),
                }
                await _api("POST", "/v1/memories", body)
                preview = arguments["content"][:120]
                return [TextContent(type="text", text=f"Stored: {preview}")]

            elif name == "recall":
                body = {
                    "agent_id": AGENTMEM_AGENT_ID,
                    "query": arguments["query"],
                    "k": arguments.get("k", 5),
                    "filters": arguments.get("filters", {}),
                }
                result = await _api("POST", "/v1/recall", body)
                return [TextContent(type="text", text=_fmt_memories(result.get("memories", [])))]

            elif name == "recall_at":
                body = {
                    "agent_id": AGENTMEM_AGENT_ID,
                    "query": arguments["query"],
                    "k": arguments.get("k", 5),
                    "as_of": arguments["as_of_iso"],
                }
                result = await _api("POST", "/v1/recall", body)
                header = f"Memories valid as of {arguments['as_of_iso'][:10]}:"
                return [TextContent(
                    type="text",
                    text=header + "\n" + _fmt_memories(result.get("memories", [])),
                )]

            elif name == "reconstruct":
                body: dict = {
                    "agent_id": AGENTMEM_AGENT_ID,
                    "as_of": arguments["as_of_iso"],
                }
                if "query" in arguments:
                    body["query"] = arguments["query"]
                result = await _api("POST", "/v1/audit/reconstruct", body)
                memories = result.get("memories", [])
                trail = result.get("event_trail", [])
                lines = [
                    f"State as of {arguments['as_of_iso'][:10]} — {len(memories)} memories:",
                    _fmt_memories(memories),
                    f"\nAudit trail: {len(trail)} events",
                ]
                for e in trail[-5:]:
                    lines.append(
                        f"  {(e.get('created_at') or '')[:19]}  "
                        f"{e.get('op','')}  id={str(e.get('memory_id') or '')[:8]}"
                    )
                return [TextContent(type="text", text="\n".join(lines))]

            return [TextContent(type="text", text=f"Unknown tool: {name}")]

        except Exception as exc:
            return [TextContent(type="text", text=f"AgentMem error ({name}): {exc}")]

    return server


async def _main() -> None:
    try:
        from mcp.server.stdio import stdio_server
    except ImportError:
        raise SystemExit(
            "MCP package not installed.  Run: pip install mcp httpx\n"
            "Or: pip install 'agentmem[mcp]'"
        )

    server = _build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(_main())
