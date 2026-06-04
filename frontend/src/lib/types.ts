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

export type JarvisEvent =
  | AgentUpdateEvent
  | TokenEvent
  | ToolCallEvent
  | VoiceStateEvent
  | AudioLevelEvent
  | MetricsEvent
  | CommsEvent
  | ToolPermissionsEvent
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
