// AgentMem TypeScript SDK — type definitions
// Mirrors the Pydantic schemas in src/agentmem/schemas.py

export interface Memory {
  id: string;
  namespace: string;
  agent_id: string;
  content: string | null;         // null if erased
  subject_id: string | null;
  event_time: string;             // ISO 8601
  ingestion_time: string;
  valid_from: string;
  valid_to: string | null;        // null = still valid
  superseded_by: string | null;
  supersession_confidence: number | null;
  barrier_group: string | null;
  importance: number;
  source: string | null;
  content_hash: string;
  erased_at: string | null;
  metadata: Record<string, unknown>;
}

export interface RecallResult {
  memories: Memory[];
  as_of: string | null;
  total_candidates: number;
}

export interface AuditEvent {
  id: string;
  op: string;                     // add | supersede | recall | erase | supersession_confirmed | supersession_rejected
  memory_id: string | null;
  content_hash: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface AuditReconstructResult {
  memories: Memory[];
  event_trail: AuditEvent[];
  as_of: string;
}

export interface EraseResult {
  subject_id: string;
  memories_erased: number;
  request_ref: string;
}

export interface MemoryBatchResult {
  added: number;
  memories: Memory[];
}

export interface SupersessionReviewItem {
  event_id: string;
  memory_id: string;
  superseded_by: string | null;
  confidence: number;
  relation: string;
  rationale: string | null;
  adjudication_stage: number;
  created_at: string;
  content_hash: string | null;
}

export interface SupersessionReviewResult {
  items: SupersessionReviewItem[];
  total: number;
  confidence_threshold: number;
}

export interface SupersessionActionResult {
  memory_id: string;
  action: "confirm" | "reject";
  applied_at: string;
}

// ── Request parameter types ──────────────────────────────────────────────────

export interface AddMemoryParams {
  agent_id: string;
  content: string;
  /** ISO 8601 timestamp of when this event occurred in the world — NOT ingestion time */
  event_time: Date | string;
  source?: string;
  subject_id?: string;
  metadata?: Record<string, string>;
  importance?: number;
}

export interface RecallParams {
  agent_id: string;
  query: string;
  k?: number;
  /** ISO 8601 — point-in-time recall; omit for current valid memories */
  as_of?: Date | string;
  filters?: Record<string, string>;
}

export interface ReconstructParams {
  agent_id: string;
  as_of: Date | string;
  query?: string;
  k?: number;
}

export interface EraseParams {
  subject_id: string;
  request_ref: string;
}

export interface ReviewSupersessionsParams {
  threshold?: number;
  limit?: number;
}

export interface AgentMemClientOptions {
  /** Base URL of the AgentMem API, e.g. https://mem.yourfirm.internal */
  url: string;
  /** API key with appropriate scopes (read / write / admin) */
  apiKey: string;
}
