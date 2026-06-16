# Building the Financial-Agent Memory Layer — Complete Engineering Spec (v2)

The explicit, build-against-it spec: file structure, data models, the supersession engine, API surface, core algorithms, security/tenancy, and phase-by-phase instructions. Stack matches your existing fluency (Python/FastAPI/Postgres/Supabase/Next.js).

**Core architectural commitment:** every memory is *bitemporal* — **event time** (when it was true in the world) and **ingestion time** (when we learned it) — held in a **split store**: an immutable audit layer (references + hashes) plus an encrypted, erasable content store. This lets us be append-only *and* honor right-to-erasure.

> **On the moat — be honest with yourself.** Bitemporal modeling is not the moat; it's a known technique (SQL:2011 temporal tables) a funded competitor could replicate in weeks. It's *table stakes for finance*, not a defense. The real, compounding moat is: (1) **regulatory trust** — reference customers who pass real audits on your trail; (2) **data gravity / system-of-record lock-in**; (3) **finance-tuned supersession** — reliable conflict detection on messy financial data (§5, the hard problem); (4) the **authored benchmark**. Build the schema because finance requires it — never pitch it as the defensibility.

---

## 0. System Overview

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Agent /    │────▶│  SDK (Python │────▶│  FastAPI service │
│  Dev's app  │     │  / TS)       │     │  (memory engine) │
└─────────────┘     └──────────────┘     └────────┬────────┘
                                                   │
        ┌───────────────────┬──────────────────────┼────────────────┬──────────────┐
        ▼                   ▼                       ▼                ▼              ▼
┌──────────────┐   ┌─────────────────┐   ┌──────────────┐  ┌──────────────┐ ┌──────────┐
│ content store│   │ event_log       │   │ subject_keys │  │ embeddings   │ │ Redis    │
│ (PG+pgvector)│   │ (append-only PG)│   │ (PG, mutable)│  │ provider     │ │ (hot mem)│
│ ENCRYPTED    │   │ AUDIT LAYER     │   │ ERASURE KEYS │  │ (Voyage API) │ │          │
└──────────────┘   └─────────────────┘   └──────────────┘  └──────────────┘ └──────────┘
```

Four operations carry the product: `add`, `recall`, `recall(as_of=...)`, and `reconstruct(...)`. Plus `erase` for compliance.

---

## 1. Locked Decisions (previously open)

| Decision | Choice | Rationale |
|---|---|---|
| **Embedding model** | **Voyage** finance/domain model (e.g. voyage-3-large or domain variant), **1024-dim** to start | Voyage leads MTEB retrieval and notably ships *domain-specific* (finance/legal/code) models that beat general-purpose by ~4–6 points — directly on-wedge. Abstract behind an interface so you can swap. |
| **Vector dimension** | **1024**, with Matryoshka truncation available | 1024 balances quality vs. storage (a 1024-d float32 vector ≈ 4KB; doubling dims doubles storage cost). Pick the model's native dim BEFORE the migration — changing a pgvector column dim later means re-embedding everything. |
| **Fallback/cheap dev embedding** | OpenAI text-embedding-3-small (1536) or local bag-of-words for tests | Cheap iteration; the interface makes provider swap a one-liner. |
| **Auth** | Hashed API keys, per-key scopes + rotation | See §7. |
| **Multi-tenancy** | Row-level via `namespace` + Postgres RLS | See §7. |
| **Subject identification** | Explicit `subject_id` on write + a PII-tagging hook | See §3.1 + §6. |

> Embedding choice is current as of mid-2026 and the market moves fast — re-confirm Voyage's current finance model name, native dimension, and price before writing the migration. The *decision to abstract the provider* matters more than the specific pick.

---

## 2. Repository Structure

```
agentmem/
├── README.md
├── docker-compose.yml            # local Postgres+pgvector, Redis
├── pyproject.toml
├── .env.example
├── alembic/                      # DB migrations
│   └── versions/
├── src/agentmem/
│   ├── __init__.py
│   ├── config.py                 # settings (env-driven)
│   ├── db.py                     # async SQLAlchemy engine/session
│   ├── models.py                 # ORM: Memory, EventLog, SubjectKey, Agent, ApiKey
│   ├── schemas.py                # Pydantic request/response models
│   ├── embeddings.py             # provider abstraction (Voyage / OpenAI / local)
│   ├── crypto.py                 # per-subject keys, encrypt/decrypt, crypto-shred
│   ├── pii.py                    # subject_id resolution + PII tagging hook
│   ├── supersession.py           # THE HARD PROBLEM — conflict detection engine
│   ├── ranking.py                # hybrid retrieval + temporal scoring
│   ├── memory_service.py         # core: add / recall / as_of orchestration
│   ├── audit.py                  # reconstruction + audit-trail builder
│   ├── api/
│   │   ├── deps.py               # auth (API key), RLS session, db deps
│   │   ├── routes_memory.py      # /v1/memories, /v1/recall
│   │   ├── routes_audit.py       # /v1/audit/*
│   │   └── routes_privacy.py     # /v1/erase
│   └── main.py                   # FastAPI app factory
├── sdk/python/agentmem_sdk/client.py
├── benchmarks/
│   ├── finance_bench.py          # authored point-in-time benchmark
│   └── supersession_eval.py      # precision/recall on conflict detection
├── examples/research_agent_demo.py
└── tests/
    ├── test_memory_service.py
    ├── test_temporal.py          # bitemporal correctness (critical)
    ├── test_supersession.py      # conflict-detection quality (critical)
    ├── test_erasure.py           # crypto-shred + audit integrity
    └── test_audit.py
```

---

## 3. Data Model

> Two stores. The audit layer holds references + hashes (never personal content, never deleted). The content store holds encrypted personal data (erasable via key destruction). Do not collapse them.

### 3.1 `memories` (content store — MUTABLE, erasable)

| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `namespace` | text, indexed | tenant isolation (RLS key) |
| `agent_id` | text, indexed | which agent owns it |
| `content_encrypted` | bytea | personal/sensitive data, encrypted with per-subject key |
| `subject_id` | text, indexed, nullable | data subject (for erasure); null if no personal data |
| `embedding` | vector(1024) | Voyage; dim matches chosen model |
| `metadata` | jsonb | NON-personal tags only (ticker, type) |
| `event_time` | timestamptz, indexed | when it was true in the world |
| `ingestion_time` | timestamptz, default now() | when we learned it |
| `valid_from` | timestamptz | start of validity window |
| `valid_to` | timestamptz, nullable | null = still valid; set on supersession |
| `superseded_by` | UUID, nullable | the newer memory |
| `supersession_confidence` | real, nullable | how sure we are it was superseded (§5) |
| `importance` | real | blended score (§4.2) |
| `source` | text | provenance |
| `content_hash` | text, indexed | hash of plaintext (dedup + integrity; survives erasure) |
| `erased_at` | timestamptz, nullable | set on crypto-shred; row becomes tombstone |

**Indexes:** `hnsw` on `embedding`; btree `(namespace, agent_id, event_time)`; btree `subject_id`; GIN `metadata`.

### 3.2 `subject_keys` (erasure mechanism — MUTABLE)

| column | type | notes |
|---|---|---|
| `subject_id` | text PK | |
| `namespace` | text | |
| `enc_key` | bytea | per-subject content key (itself encrypted with a master KMS key) |
| `created_at` | timestamptz | |
| `destroyed_at` | timestamptz, nullable | set to crypto-shred ALL of a subject's data at once |

### 3.3 `event_log` (audit layer — APPEND-ONLY, never updated)

| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `namespace` | text | |
| `agent_id` | text | |
| `op` | text | `add` / `supersede` / `recall` / `erase` |
| `memory_id` | UUID | reference only |
| `content_hash` | text | integrity proof, survives erasure |
| `payload` | jsonb | NON-personal metadata only (query terms, ids, scores, sources, confidences) |
| `created_at` | timestamptz | immutable |

### 3.4 Reconciling append-only with right-to-erasure

| Requirement | Mechanism |
|---|---|
| Right to erasure (GDPR Art. 17 / CCPA) | Crypto-shred subject key → content unreadable, audit intact |
| Financial retention mandates (SEC 17a-4, MiFID II) | Legal-obligation exemption can override erasure for *specific regulated data* — scope by counsel, per jurisdiction/data-type. NOT blanket. |
| Audit integrity after erasure | Tombstone (`erased_at`) + `erase` log row + retained `content_hash` prove the trail wasn't altered |
| Configurable retention | Per-customer, jurisdiction-aware retention on content store; audit layer retained per regulation |

> **Legal caveat:** mechanisms are sound and standard; *boundaries* (which rule mandates retention of which data, overriding which right, where) are questions for a privacy/regulatory lawyer. Build to be *capable* of all four; let counsel set policy. Never promise compliance ahead of counsel.

### 3.5 Supporting tables
- `agents` (agent_id, namespace, created_at, config)
- `api_keys` (id, hashed_key, namespace, scopes jsonb, created_at, rotated_at, revoked_at)

---

## 4. Retrieval & Ranking

### 4.1 Hybrid retrieval (`ranking.py`)
```
score = w_sem * semantic_similarity   # pgvector cosine
      + w_lex * lexical_match          # BM25 / ts_rank over decrypted content (in-process)
      + w_rec * recency_decay          # exp decay on event_time
      + w_imp * importance
```
Start `w_sem=0.5, w_lex=0.2, w_rec=0.15, w_imp=0.15`; tune against the benchmark. **When `as_of` is set, apply the temporal validity filter BEFORE ranking.** In present-time recall (no `as_of`), blend validity so a currently-valid fact outranks a superseded one of similar relevance (the bug the local PoC caught).

> Note: lexical/BM25 over *encrypted* content requires decrypting candidates in-process after a vector prefilter, or maintaining a separate searchable non-PII index. Decide per deployment; for finance facts that aren't personal data, much content can be indexed directly.

### 4.2 Importance (multi-signal, NOT pure-LLM)
```
importance = 0.3*recency + 0.25*retrieval_frequency
           + 0.2*explicit_salience + 0.15*semantic_centrality
           + 0.1*optional_llm_score
```
`confidence` tracked separately — low when signals disagree or data is sparse. Surface both in the dashboard. Reserve LLM scoring for ambiguous/batch cases (cost discipline).

### 4.3 Lifecycle / cost control
- TTL + importance eviction from the **hot (Redis) layer only**; content store + audit layer persist per retention policy.
- Periodic summarization of old low-importance memories into compressed form (batch), but always retain originals + audit trail.

---

## 5. The Supersession Engine (`supersession.py`) — THE HARD PROBLEM

> This is the riskiest, most defensible part. The local PoC hand-declares supersession via an explicit topic; real data doesn't. Deciding *what supersedes what* — across paraphrases ("guidance raised to $36B" vs "Q3 outlook now $36B"), partial updates, and genuine contradictions vs. mere additions — is where the moat lives. **Prototype this before the dashboard. Do not claim it works until measured.**

### 5.1 The recommended design: a 3-stage hybrid funnel
Pure-embedding similarity is too blunt (it can't tell "raised to $36B" from "lowered to $28B" — both are highly similar to the old fact). Pure-LLM is too slow/expensive at write scale. So: a cheap funnel that narrows candidates, then an expensive adjudicator only on the hard few.

**Stage 1 — Candidate generation (cheap, deterministic).**
On `add`, find prior *valid* memories that could be about the same fact:
- Same structured key in `metadata` (e.g. `ticker=NVDA` + `metric=guidance`). For finance this is powerful — most facts have a natural entity+attribute key.
- AND semantic similarity above a recall-tuned threshold (cast wide; favor recall over precision here).

**Stage 2 — Relation classification (medium).**
For each candidate pair (old, new), classify the relation:
- `SUPERSEDES` — same entity+attribute, new event_time ≥ old, values differ → close the old one.
- `CONFIRMS` — same value → boost importance/confidence, no supersession.
- `ADDS` — related but distinct attribute → keep both, no supersession.
- `CONTRADICTS_SAME_TIME` — conflicting values with overlapping validity and no clear ordering → flag for review, store both, lower confidence.

Do this with deterministic rules wherever the metadata is structured (finance gives you this often), and fall through to Stage 3 only when rules are ambiguous.

**Stage 3 — LLM adjudication (expensive, rare).**
Only for ambiguous pairs Stage 2 can't resolve, call an LLM with a tight prompt: "Does fact B supersede fact A, confirm it, add to it, or contradict it? Return JSON {relation, confidence, rationale}." Cache by content-hash pair so you never adjudicate the same pair twice. Write the rationale + confidence into the event log (auditable).

### 5.2 Confidence is first-class
Every supersession carries `supersession_confidence`. Low-confidence supersessions are surfaced (dashboard) for human confirmation rather than applied silently. In finance, a wrong silent supersession (dropping the old number) is the exact failure you're selling against — so bias toward *flag, don't auto-drop* when unsure.

### 5.3 Measuring it (`benchmarks/supersession_eval.py`)
You cannot claim this works without a labeled test set. Build one:
- Curate real sequences: earnings revisions, rating changes, restatements, guidance updates, plus *distractors* (related-but-not-superseding facts).
- Label the correct relation for each pair.
- Measure **precision and recall on "SUPERSEDES" detection** separately. Recall matters (missing a supersession = stale fact returned); precision matters more in finance (a false supersession = silently dropping a true fact).
- Track the metric over time; it's both your internal quality gate and external marketing (the authored benchmark).

### 5.4 Test cases that must pass (`test_supersession.py`)
- Paraphrased supersession detected (different words, same fact updated).
- Opposite-direction update detected ("raised" vs "lowered" both supersede, correctly).
- Additive fact NOT treated as supersession (new attribute on same entity).
- Same-time contradiction flagged, both retained, neither silently dropped.
- Property test: across random update sequences, `recall(as_of=t)` never returns a fact outside its validity window.

---

## 6. PII & Subject Identification (`pii.py`)

The erasure model is only as good as knowing *whose* data a memory contains. Two-layer approach:
1. **Explicit:** the SDK lets the caller pass `subject_id` on write (best — the app usually knows).
2. **Hook:** an optional PII-detection pass that flags likely personal data and assigns/links a `subject_id`, so erasure still works when callers don't tag. Start with explicit; add detection later.

On write: if `subject_id` present → fetch/create its key, encrypt content. If no personal data → `subject_id` null, content may be stored unencrypted (finance facts like prices aren't personal). This keeps non-PII directly searchable and only encrypts what erasure must cover.

---

## 7. Security & Multi-Tenancy

- **Auth:** API keys, stored hashed (never plaintext). Each key has `scopes` (read/write/admin) and supports rotation (`rotated_at`) and revocation (`revoked_at`). Validate + resolve namespace in `deps.py`.
- **Multi-tenancy:** row-level isolation via `namespace` + Postgres **Row-Level Security** policies, so a query can never cross tenants even on a bug. Set the tenant on the session in `deps.py`.
- **Key management:** per-subject `enc_key` is itself encrypted with a master key held in a KMS (not in the DB). Crypto-shred = destroy the per-subject key; master key never leaves KMS.
- **Encryption at rest** for the content store; TLS in transit. SOC 2 path started in Phase 3.

---

## 8. API Surface

### `POST /v1/memories` — add
```json
{ "agent_id": "research-1", "content": "NVDA Q3 guidance raised to $36B",
  "event_time": "2026-05-10T00:00:00Z", "source": "analyst_day",
  "subject_id": null, "metadata": {"ticker": "NVDA", "metric": "guidance"} }
```
Flow: resolve subject/key → embed → run supersession funnel (§5) → on SUPERSEDES, set old `valid_to`/`superseded_by`/`supersession_confidence` → insert new → write `add` (+ `supersede`) rows to event_log.

### `POST /v1/recall` — retrieve
```json
{ "agent_id": "research-1", "query": "NVDA guidance?", "k": 5,
  "as_of": "2026-05-09T00:00:00Z", "filters": {"ticker": "NVDA"} }
```
No `as_of` → current valid, hybrid-ranked. With `as_of` → only memories whose validity window contains `as_of`. Logs the recall.

### `GET /v1/audit/reconstruct` — the compliance product
```
?agent_id=research-1&as_of=2026-05-09T00:00:00Z&query=...
```
Returns the exact memory set + event-log trail behind a past decision: timestamped, sourced, reconstructable.

### `POST /v1/erase` — right-to-erasure
```json
{ "subject_id": "person-123", "request_ref": "GDPR-req-4471" }
```
Crypto-shred the subject key → content unreadable; set `erased_at` (tombstone); write immutable `erase` row with `request_ref`. Audit structure/hashes/references survive. Subject to retention overrides set by counsel.

---

## 9. Phase-by-Phase Build

### Phase 1 — Core engine (Weeks 1–4)
1. `docker-compose up` pgvector + Redis; confirm `SELECT '[1,2,3]'::vector;`.
2. `models.py` + first migration (all tables, **lock the 1024 dim now**).
3. `embeddings.py` provider interface; wire Voyage (or dev fallback).
4. `crypto.py` + `pii.py`: per-subject keys, encrypt/decrypt, subject resolution.
5. `memory_service.add()` with a FIRST-CUT supersession (Stage 1+2 rules only) + event-log writes. **`test_temporal.py`.**
6. `recall()` + hybrid ranking, then `as_of` filter.
7. `audit.reconstruct()`. Record the side-by-side demo.

### Phase 2 — Supersession depth + SDK + API (Weeks 4–7)
1. Build the labeled supersession test set + `supersession_eval.py`. Add Stage 3 LLM adjudication. Iterate until precision/recall clear your bar. **`test_supersession.py`.**
2. FastAPI routes + API-key auth + RLS in `deps.py`.
3. Python SDK + **local mode** (zero-signup against local PG).
4. One framework adapter (verify current fintech-agent framework momentum first).
5. <10-min finance quickstart.

### Phase 3 — Hosted + erasure + dashboard (Weeks 7–11)
1. Deploy on a managed platform (Render/Fly/Railway); no Kubernetes yet.
2. Stripe metering (memories stored + recalls).
3. **Erasure path** (`/v1/erase`, KMS master key, crypto-shred) + `test_erasure.py`. Counsel defines retention-override scope.
4. Audit dashboard (Next.js): what was recalled, why (score + supersession confidence), as-of-when.
5. SOC 2 path; encryption at rest; data-residency option.

### Phase 4 — Differentiators (Weeks 11+)
1. Publish the authored finance memory benchmark (point-in-time correctness + audit completeness + supersession quality).
2. Multi-agent shared memory + access control (information barriers between desks).
3. Temporal abstraction at scale.
4. Framework-agnostic adapters.

---

## 10. Testing Priorities (don't skip)
- `test_temporal.py` — bitemporal correctness under supersession. The bug class that kills trust.
- `test_supersession.py` — conflict-detection quality; precision ≥ recall bias in finance.
- `test_erasure.py` — crypto-shred renders content unreadable AND audit reconstruction still proves existence/timing.
- `test_audit.py` — reconstruction completeness; event log never mutated.
- Property tests on `as_of` — never return a fact outside its validity window.

---

## 11. First-Week Concrete Checklist
1. `git init`, scaffold §2.
2. `docker-compose.yml` (pgvector + Redis); confirm vector type works.
3. `models.py` + migration; **1024-dim locked**; tables exist.
4. `embeddings.py` returning real Voyage vectors for a test string (dev fallback wired too).
5. `crypto.py`: encrypt/decrypt round-trip + crypto-shred makes content unreadable (unit test).
6. `memory_service.add()` + `recall()` (no `as_of`) + happy-path test.
7. `as_of` filter + `test_temporal.py`.
8. First-cut Stage 1+2 supersession on three hand-built cases.

---

*Build order in one line: local PG+pgvector → split-store bitemporal model (1024-dim locked) → crypto/PII → add with first-cut supersession + event log → hybrid recall → as-of recall → audit reconstruction → supersession depth (the hard problem, measured) → SDK + local mode → adapter → hosted + erasure + dashboard → benchmark. Build/test the bitemporal core, audit trail, supersession engine, and erasure path first and hardest — they're table stakes for finance. The moat is what accumulates on top: regulatory trust, data gravity, finance-tuned supersession, and the benchmark.*
