/**
 * Shared frontend types — mirror the backend WebSocket event schema defined in
 * `backend/events.py`. Keeping these in lockstep with the backend is critical:
 * the store dispatches on the `type` discriminator below.
 */

export type VoiceState = "idle" | "listening" | "thinking" | "speaking";

export type AgentStatus = "idle" | "working" | "error" | "offline";

/** Backend `agent_update` event. */
export interface AgentUpdateEvent {
  type: "agent_update";
  agent_id: string;
  agent_name: string;
  status: AgentStatus;
  current_task: string | null;
  timestamp: string;
}

/** Backend `token` event — one streamed token of an AI response. */
export interface TokenEvent {
  type: "token";
  content: string;
  model: string;
  is_final: boolean;
  timestamp: string;
}

/** Backend `tool_call` event — an agent invoked a tool. */
export interface ToolCallEvent {
  type: "tool_call";
  tool_name: string;
  agent_id: string;
  args: Record<string, unknown>;
  result: unknown | null;
  timestamp: string;
}

/** Backend `voice_state` event — drives the orb colour. */
export interface VoiceStateEvent {
  type: "voice_state";
  state: VoiceState;
  timestamp: string;
}

/**
 * Optional richer events the backend may add later for the Reasoning,
 * Communications and Tools windows. They are forward-declared so the store can
 * already route them; absence of a handler is harmless.
 */
export interface MetricsEvent {
  type: "metrics";
  cost_usd: number;
  latency_ms: number;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  timestamp: string;
}

/**
 * Backend `audio_level` event — emitted every ~50ms while TTS plays. Drives the
 * orb's amplitude pulse during the speaking state. `level` is normalised 0..1.
 */
export interface AudioLevelEvent {
  type: "audio_level";
  level: number;
  timestamp: string;
}

export interface SlackMessage {
  id: string;
  sender: string;
  channel: string;
  text: string;
  unread: boolean;
  timestamp: string;
}

export interface GmailMessage {
  id: string;
  sender: string;
  subject: string;
  snippet: string;
  unread: boolean;
  timestamp: string;
}

export interface CommsEvent {
  type: "comms";
  slack?: SlackMessage[];
  gmail?: GmailMessage[];
}

export interface ToolPermissionsEvent {
  type: "tool_permissions";
  /** agent_id -> list of tool names that agent may use. */
  permissions: Record<string, string[]>;
  /** optional canonical list of all tool names. */
  tools?: string[];
}

export interface ShutdownEvent {
  type: "shutdown";
  timestamp: string;
}

/* ── Memory graph (Window 6 — the 3D "memory brain") ───────────────────────
 * Mirrors `GET /api/memory/graph`. Nodes are an open union keyed on `type`
 * so a future `project` source slots in without reshaping the payload. The
 * shared fields below appear on every node; the rest are type-specific. */

/** Fields present on every graph node regardless of source. */
interface MemoryNodeBase {
  id: string;
  type: string;
  created_at?: string | null;
}

/** A distilled memory fact (`type: "memory"`). */
export interface MemoryFactNode extends MemoryNodeBase {
  type: "memory";
  text_preview: string;
  text_full: string;
  importance: number; // 0..1
  access_count: number;
  confidence: number; // 0..1
  last_recalled_at: string | null;
  conflicting_fact_ids: string | null;
  subject: string | null;
  /** Legacy signal-category string (kept for back-compat). */
  category?: string | null;
  /** One of the 10 locked categories — drives the node's base color. */
  domain?: string | null;
}

/** A person profile (`type: "person"`). */
export interface MemoryPersonNode extends MemoryNodeBase {
  type: "person";
  name: string;
  email?: string | null;
  role?: string | null;
  notes?: string | null;
  last_contact_at?: string | null;
}

/** Any future/unknown node type still carries the base fields. */
export interface MemoryGenericNode extends MemoryNodeBase {
  [key: string]: unknown;
}

export type MemoryNode = MemoryFactNode | MemoryPersonNode | MemoryGenericNode;

export interface MemoryEdge {
  source_id: string;
  target_id: string;
  similarity: number; // 0.5..1
}

export interface MemoryGraph {
  nodes: MemoryNode[];
  edges: MemoryEdge[];
}

/** Backend `memory_update` event — grows/updates the brain live. */
export interface MemoryUpdateEvent {
  type: "memory_update";
  action: "add" | "update" | "recall";
  node: MemoryNode | null;
  timestamp: string;
}

/**
 * Backend `memory_recall` event — Helix recalled these facts to answer a
 * question. Each id matches a graph node `id` (e.g. "fact:12"). The brain
 * flashes the matching neurons. One or many ids may be listed.
 */
export interface MemoryRecallEvent {
  type: "memory_recall";
  fact_ids: string[];
  timestamp: string;
}

/**
 * Backend `memory_confirm` event — Helix is unsure whether to remember a fact
 * and asks the user to confirm via the Reasoning window. `category` here is the
 * DOMAIN (drives the badge color). `fact` is untrusted display-only text — it
 * must never be echoed back into a model prompt.
 */
export interface MemoryConfirmEvent {
  type: "memory_confirm";
  confirm_id: string;
  fact: string;
  category: string;
  subject?: string | null;
  timestamp: string;
}

export type HelixEvent =
  | AgentUpdateEvent
  | TokenEvent
  | ToolCallEvent
  | VoiceStateEvent
  | AudioLevelEvent
  | MetricsEvent
  | CommsEvent
  | ToolPermissionsEvent
  | MemoryUpdateEvent
  | MemoryRecallEvent
  | MemoryConfirmEvent
  | ShutdownEvent;

/** A tool-call record as held in the store (args + eventual result). */
export interface ToolCallRecord {
  id: string;
  tool_name: string;
  agent_id: string;
  args: Record<string, unknown>;
  result: unknown | null;
  timestamp: string;
}

/** An agent as held in the store, including its accumulated task history. */
export interface AgentState {
  agent_id: string;
  agent_name: string;
  role: string;
  status: AgentStatus;
  current_task: string | null;
  history: string[];
}

export type ConnectionStatus = "connecting" | "open" | "closed";
