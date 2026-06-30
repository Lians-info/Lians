# Changelog

All notable changes to Lians. Versions follow semver; SDKs are released in lock-step.

## 0.3.0 — 2026-06-29

The production-readiness + competitive release. Everything below is on `master`
with full CI (12 checks across 5 languages + Postgres).

### Added
- **Agent memory harness** (`LiansMemoryHarness`) — drop-in recall-before /
  remember-after loop with compliance scoping.
- **Relationship graph** — `relate` / `unrelate` / `neighbors` / `path` (bitemporal,
  point-in-time), **graph-proximity (node-distance) reranking**, and `POST
  /v1/graph/extract` (rule-based text→edges, opt-in LLM).
- **MMR reranking** and `POST /v1/context` — token-budgeted, ready-to-inject block.
- **Three new SDKs — Go, Java, and C** — now five languages (Python, TypeScript,
  Go, Java, C). npm package renamed to `@lians-ai/lians`.
- **Exactly-once writes** — `Idempotency-Key` on `POST /v1/memories`; SDK
  retry/backoff with an auto idempotency key.
- **RBAC roles** (`owner`/`analyst`/`compliance`/`readonly`) on API keys.
- **SIEM audit streaming** (`SIEM_URL`) + `/livez` and `/readyz` probes.
- Memory **evaluation harness** (LoCoMo/LongMemEval shape, judge-free).
- Claude Code plugin, Codex integration, cross-tool skills.
- Docs: security whitepaper, STRIDE threat model, SOC 2/HIPAA readiness, SSO,
  publishing, and mem0 / Zep comparisons.

### Fixed (correctness / security)
- **Information barriers now enforced at the database layer.** Barrier RLS policies
  are `RESTRICTIVE` (migration 0013) and the barrier session var is set per
  request; cross-barrier denial is proven in CI against a non-superuser role.
  Previously isolation was app-layer only.
- Restored `memory_service` functions the API imported but lacked (snapshot,
  lineage, fact-history, conflicts, erasure certificate); wired conflict
  persistence and webhook dispatch.
- Fixed the migration runner (asyncpg multi-statement / parameterized `SET`) and a
  stack of CI environment issues — CI is green for the first time.

> **Deployment note:** run the application as a **non-superuser, non-BYPASSRLS**
> Postgres role, or RLS (namespace + barrier isolation) is silently bypassed.

## 0.2.0 — 2026-06-27

Free tier, cloud pricing, GitHub org migration to `Lians-ai`.
