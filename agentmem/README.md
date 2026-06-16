# AgentMem

Financial-agent memory layer with bitemporal validity, audit reconstruction,
first-cut finance supersession, and crypto-shred erasure.

## What is built

- Split content/audit model: `memories`, `subject_keys`, immutable-style `event_log`.
- Bitemporal recall: present-time ranking and `as_of` historical snapshots.
- Supersession funnel: structured finance keys plus deterministic relation rules.
- Erasure path: per-subject encryption keys, tombstones, retained audit hashes.
- FastAPI API: `/v1/memories`, `/v1/recall`, `/v1/audit/reconstruct`, `/v1/erase`.
- Python SDK and local deterministic embeddings for tests/dev.
- Alembic initial migration with 1024-dimension pgvector column.
- Benchmarks for point-in-time recall and supersession detection.

## Quickstart

```powershell
cd agentmem
copy .env.example .env
docker compose up -d
python -m pip install -e ".[dev]"
python -m pytest
uvicorn src.agentmem.main:app --reload
```

The default `.env.example` uses the local deterministic embedding provider, so no
external API key is required for tests.

## API key setup for local API testing

Create an `api_keys` row with the SHA-256 hash of the key you want to send in
`X-API-Key`. Give it scopes like `["read", "write", "admin"]` and a namespace
such as `dev`.

## Production notes

Confirm the current Voyage finance model name, native dimensions, and pricing
before production migration rollout. The provider interface is intentionally
thin so Voyage, OpenAI, or local test embeddings can be swapped without changing
the memory service.
