import type {
  Memory,
  RecallResult,
  AuditReconstructResult,
  EraseResult,
  MemoryBatchResult,
  SupersessionReviewResult,
  SupersessionActionResult,
  AddMemoryParams,
  RecallParams,
  ReconstructParams,
  EraseParams,
  ReviewSupersessionsParams,
  AgentMemClientOptions,
} from "./types.js";

function toIso(dt: Date | string): string {
  return typeof dt === "string" ? dt : dt.toISOString();
}

export class AgentMemClient {
  private readonly url: string;
  private readonly apiKey: string;

  constructor(options: AgentMemClientOptions) {
    this.url = options.url.replace(/\/$/, "");
    this.apiKey = options.apiKey;
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
  ): Promise<T> {
    const res = await fetch(`${this.url}${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": this.apiKey,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    if (!res.ok) {
      const detail = await res.text().catch(() => res.statusText);
      throw new Error(`AgentMem ${method} ${path} → ${res.status}: ${detail}`);
    }

    if (res.status === 204) return undefined as unknown as T;
    return res.json() as Promise<T>;
  }

  // ── Write ──────────────────────────────────────────────────────────────────

  /** Store a financial fact, observation, or decision with its event timestamp. */
  async add(params: AddMemoryParams): Promise<Memory> {
    return this.request<Memory>("POST", "/v1/memories", {
      ...params,
      event_time: toIso(params.event_time),
    });
  }

  /**
   * Add multiple memories in a single request.
   * Items are processed sequentially so a later item can supersede an earlier one
   * in the same batch (e.g. loading a time-series of revisions in order).
   */
  async batchAdd(memories: AddMemoryParams[]): Promise<MemoryBatchResult> {
    return this.request<MemoryBatchResult>("POST", "/v1/memories/batch", {
      memories: memories.map((m) => ({ ...m, event_time: toIso(m.event_time) })),
    });
  }

  // ── Read ───────────────────────────────────────────────────────────────────

  /**
   * Retrieve the most relevant CURRENT memories for a query.
   * Superseded facts are excluded. Optionally filter by metadata fields.
   */
  async recall(params: RecallParams): Promise<RecallResult> {
    return this.request<RecallResult>("POST", "/v1/recall", {
      ...params,
      as_of: params.as_of ? toIso(params.as_of) : undefined,
    });
  }

  /**
   * Retrieve memories that were valid at a specific past point in time.
   *
   * This is the compliance differentiator — neither mem0 nor Zep support this.
   * Use for audit queries: "What guidance did we have on 2026-03-01?"
   * Later superseding updates are excluded from the result set.
   */
  async recallAt(
    agent_id: string,
    query: string,
    as_of: Date | string,
    k = 5,
  ): Promise<RecallResult> {
    return this.recall({ agent_id, query, k, as_of });
  }

  /**
   * Reconstruct the complete memory state and audit event trail at a past timestamp.
   *
   * Returns every memory that was valid at `as_of` plus the timestamped, content-
   * hashed event log that proves what the agent knew and when.  Use for regulatory
   * audit submissions and pre/post-trade reconstruction.
   */
  async reconstruct(params: ReconstructParams): Promise<AuditReconstructResult> {
    const body = {
      agent_id: params.agent_id,
      as_of: toIso(params.as_of),
      ...(params.query && { query: params.query }),
      ...(params.k && { k: params.k }),
    };
    return this.request<AuditReconstructResult>("POST", "/v1/audit/reconstruct", body);
  }

  // ── Compliance ─────────────────────────────────────────────────────────────

  /**
   * Crypto-shred a data subject: destroys their per-subject encryption key so all
   * their memories become unreadable. The audit trail (content hashes, timestamps)
   * is preserved to prove the erasure without revealing the content.
   *
   * GDPR Article 17 / CCPA right-to-erasure.
   */
  async erase(params: EraseParams): Promise<EraseResult> {
    return this.request<EraseResult>("POST", "/v1/erase", params);
  }

  // ── Supersession review ────────────────────────────────────────────────────

  /**
   * Return supersession events whose confidence is below the threshold.
   *
   * Financial firms should poll this (or webhook it) to catch cases where the
   * engine was uncertain about replacing an old fact.  A wrong silent supersession
   * — dropping a real number — is the failure mode you're selling against.
   */
  async reviewSupersessions(
    params: ReviewSupersessionsParams = {},
  ): Promise<SupersessionReviewResult> {
    const qs = new URLSearchParams();
    if (params.threshold !== undefined) qs.set("threshold", String(params.threshold));
    if (params.limit !== undefined) qs.set("limit", String(params.limit));
    const q = qs.toString() ? `?${qs}` : "";
    return this.request<SupersessionReviewResult>("GET", `/v1/supersessions/review${q}`);
  }

  /**
   * Confirm a supersession — the engine was correct.
   * Writes an immutable audit event with the reviewer's note; no data changes.
   */
  async confirmSupersession(
    memoryId: string,
    reviewerNote?: string,
  ): Promise<SupersessionActionResult> {
    return this.request<SupersessionActionResult>(
      "PATCH",
      `/v1/supersessions/${memoryId}`,
      { action: "confirm", reviewer_note: reviewerNote },
    );
  }

  /**
   * Reject a supersession — the engine was wrong.
   * Restores the old memory as currently valid (valid_to = NULL) and writes an
   * immutable audit event.  Both old and new memories are now treated as additive.
   */
  async rejectSupersession(
    memoryId: string,
    reviewerNote?: string,
  ): Promise<SupersessionActionResult> {
    return this.request<SupersessionActionResult>(
      "PATCH",
      `/v1/supersessions/${memoryId}`,
      { action: "reject", reviewer_note: reviewerNote },
    );
  }
}
