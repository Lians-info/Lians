/**
 * LangChain.js integration for AgentMem.
 *
 * Two integration patterns:
 *
 * 1. AgentMemChatHistory — implements BaseChatMessageHistory for
 *    RunnableWithMessageHistory.  Stores conversation turns as AgentMem
 *    memories; supports per-session isolation.
 *
 * 2. buildAgentMemTools — three StructuredTools for ReAct agents and
 *    LangGraph nodes: remember, recall, recall_at.  The recall_at tool is
 *    the differentiating one — point-in-time recall that neither mem0 nor Zep
 *    support.
 *
 * Install:
 *   npm install @langchain/core agentmem-sdk
 *
 * Usage — chat history:
 *
 *   import { AgentMemClient } from "agentmem-sdk";
 *   import { AgentMemChatHistory } from "agentmem-sdk/langchain";
 *   import { RunnableWithMessageHistory } from "@langchain/core/runnables";
 *
 *   const client = new AgentMemClient({ url: "...", apiKey: "..." });
 *   const chain = new RunnableWithMessageHistory(
 *     yourChain,
 *     (sessionId) => new AgentMemChatHistory({ client, sessionId }),
 *   );
 *
 * Usage — agent tools:
 *
 *   import { buildAgentMemTools } from "agentmem-sdk/langchain";
 *   const tools = buildAgentMemTools({ client, agentId: "research-agent" });
 */

import type { AgentMemClient } from "./client.js";
import type { BaseMessage } from "@langchain/core/messages";

// ── Chat history ─────────────────────────────────────────────────────────────

export interface AgentMemChatHistoryOptions {
  client: AgentMemClient;
  sessionId: string;
  agentId?: string;
  maxMessages?: number;
}

/**
 * LangChain chat message history backed by AgentMem.
 *
 * Each conversation turn is stored as a memory with metadata:
 *   { session_id: sessionId, msg_type: "human" | "ai" }
 *
 * Messages are returned in chronological order (sorted by event_time).
 */
export class AgentMemChatHistory {
  private client: AgentMemClient;
  private sessionId: string;
  private agentId: string;
  private maxMessages: number;

  constructor(options: AgentMemChatHistoryOptions) {
    this.client = options.client;
    this.sessionId = options.sessionId;
    this.agentId = options.agentId ?? "chat";
    this.maxMessages = options.maxMessages ?? 100;
  }

  async getMessages(): Promise<BaseMessage[]> {
    const { messages } = await import("@langchain/core/messages");
    const result = await this.client.recall({
      agent_id: this.agentId,
      query: "conversation message",
      k: this.maxMessages,
      filters: { session_id: this.sessionId },
    });

    // Sort chronologically — recall returns by relevance score
    const sorted = [...result.memories].sort((a, b) =>
      a.event_time.localeCompare(b.event_time),
    );

    const out: BaseMessage[] = [];
    for (const m of sorted) {
      if (!m.content) continue;
      try {
        const { messagesFromDict } = await import("@langchain/core/messages");
        const parsed = messagesFromDict([JSON.parse(m.content)]);
        out.push(...parsed);
      } catch {
        // Skip unparseable memories
      }
    }
    return out;
  }

  async addMessage(message: BaseMessage): Promise<void> {
    const { messageToDict } = await import("@langchain/core/messages");
    await this.client.add({
      agent_id: this.agentId,
      content: JSON.stringify(messageToDict(message)),
      event_time: new Date(),
      source: "langchain_chat",
      metadata: {
        session_id: this.sessionId,
        msg_type: message._getType(),
      },
    });
  }

  async addMessages(messages: BaseMessage[]): Promise<void> {
    const base = Date.now();
    await this.client.batchAdd(
      messages.map(async (msg, i) => {
        const { messageToDict } = await import("@langchain/core/messages");
        return {
          agent_id: this.agentId,
          content: JSON.stringify(messageToDict(msg)),
          event_time: new Date(base + i),
          source: "langchain_chat",
          metadata: {
            session_id: this.sessionId,
            msg_type: msg._getType(),
          },
        };
      }) as unknown as Parameters<AgentMemClient["batchAdd"]>[0],
    );
  }

  /** AgentMem audit trail is immutable. For GDPR erasure use client.erase(). */
  async clear(): Promise<void> {}
}

// ── Agent tools ──────────────────────────────────────────────────────────────

export interface BuildAgentMemToolsOptions {
  client: AgentMemClient;
  agentId: string;
}

function formatMemories(
  memories: Awaited<ReturnType<AgentMemClient["recall"]>>["memories"],
): string {
  if (!memories.length) return "No relevant memories found.";
  return memories
    .map((m) => `[${(m.event_time ?? "").slice(0, 10)}] ${m.content ?? "[erased]"}`)
    .join("\n");
}

/**
 * Build three LangChain tools wired to an AgentMem client.
 *
 * remember   — store a fact with its event timestamp
 * recall     — retrieve current relevant memories by semantic search
 * recall_at  — retrieve memories valid at a specific past date (compliance)
 *
 * @example
 * const tools = buildAgentMemTools({ client, agentId: "research-agent" });
 * const agent = createReactAgent({ llm, tools, prompt });
 */
export async function buildAgentMemTools(
  options: BuildAgentMemToolsOptions,
): Promise<unknown[]> {
  const { DynamicStructuredTool } = await import("@langchain/core/tools");
  const { z } = await import("zod");
  const { client, agentId } = options;

  const rememberTool = new DynamicStructuredTool({
    name: "remember",
    description:
      "Store a financial fact, observation, or decision in persistent memory. " +
      "Always provide event_time_iso as when the event occurred, not now. " +
      "Add ticker/metric metadata for precise supersession detection.",
    schema: z.object({
      content: z.string().describe("The fact or observation to remember."),
      event_time_iso: z
        .string()
        .describe("ISO 8601 timestamp of when this event occurred."),
      metadata: z
        .record(z.string())
        .optional()
        .describe("Tags: ticker, metric, entity, instrument."),
      source: z
        .string()
        .optional()
        .describe("Provenance: earnings_call, analyst_report, etc."),
    }),
    func: async ({ content, event_time_iso, metadata, source }) => {
      await client.add({
        agent_id: agentId,
        content,
        event_time: event_time_iso,
        source: source ?? "langchain_agent",
        metadata: metadata ?? {},
      });
      return `Stored: ${content.slice(0, 120)}`;
    },
  });

  const recallTool = new DynamicStructuredTool({
    name: "recall",
    description:
      "Retrieve the most relevant CURRENT memories for a query. " +
      "Returns only presently-valid facts — superseded facts are excluded. " +
      "Call this before answering any question that may be in memory.",
    schema: z.object({
      query: z.string().describe("Natural-language query."),
      k: z.number().int().min(1).max(20).optional().default(5),
      filters: z
        .record(z.string())
        .optional()
        .describe("Metadata equality filters, e.g. { ticker: 'NVDA' }"),
    }),
    func: async ({ query, k, filters }) => {
      const result = await client.recall({
        agent_id: agentId,
        query,
        k,
        filters,
      });
      return formatMemories(result.memories);
    },
  });

  const recallAtTool = new DynamicStructuredTool({
    name: "recall_at",
    description:
      "Retrieve memories that were valid at a specific point in time. " +
      "Use for compliance and audit: 'What guidance did we have on 2026-03-01?' " +
      "Later superseding updates are excluded — true point-in-time recall.",
    schema: z.object({
      query: z.string().describe("Natural-language query."),
      as_of_iso: z
        .string()
        .describe("ISO 8601 timestamp for the point-in-time snapshot."),
      k: z.number().int().min(1).max(20).optional().default(5),
    }),
    func: async ({ query, as_of_iso, k }) => {
      const result = await client.recall({
        agent_id: agentId,
        query,
        k,
        as_of: as_of_iso,
      });
      return (
        `Memories valid as of ${as_of_iso.slice(0, 10)}:\n` +
        formatMemories(result.memories)
      );
    },
  });

  return [rememberTool, recallTool, recallAtTool];
}
