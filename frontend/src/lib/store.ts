/**
 * Global Zustand store — the single source of UI truth for all 5 windows.
 *
 * State is driven almost entirely by WebSocket events from the backend
 * (`backend/events.py`). The only "hardcoded" values here are the canonical
 * roster of 6 agents and the tool/agent matrix scaffold, which exist so the
 * windows render a meaningful skeleton before the first event arrives. Every
 * such value is *overwritten* by live WebSocket data as soon as it lands — the
 * UI never invents agent activity, tokens, messages, or tool results.
 */

import { create } from "zustand";
import type {
  AgentState,
  AgentStatus,
  ConnectionStatus,
  GmailMessage,
  SlackMessage,
  ToolCallRecord,
  VoiceState,
} from "./types";

/** Canonical agent roster (ids + names + roles mirror the backend agents). */
const INITIAL_AGENTS: AgentState[] = [
  { agent_id: "production_lead", agent_name: "Atlas", role: "Production Lead", status: "offline", current_task: null, history: [] },
  { agent_id: "frontend", agent_name: "Ben", role: "Frontend", status: "offline", current_task: null, history: [] },
  { agent_id: "backend", agent_name: "Kado", role: "Backend", status: "offline", current_task: null, history: [] },
  { agent_id: "security", agent_name: "Sentinel", role: "Security", status: "offline", current_task: null, history: [] },
  { agent_id: "marketing", agent_name: "Vega", role: "Marketing", status: "offline", current_task: null, history: [] },
  { agent_id: "content", agent_name: "Quill", role: "Content Creator", status: "offline", current_task: null, history: [] },
];

/** Canonical tool list — mirrors the 12 tools registered in backend wiring. */
export const ALL_TOOLS: string[] = [
  "web_search",
  "browse_url",
  "read_file",
  "write_file",
  "list_files",
  "execute_code",
  "slack_send_message",
  "slack_get_unread_mentions",
  "gmail_get_inbox",
  "gmail_draft_email",
];

/** Default per-agent permission matrix — mirrors backend DEFAULT_PERMISSIONS. */
const INITIAL_PERMISSIONS: Record<string, string[]> = {
  production_lead: [...ALL_TOOLS],
  frontend: ["web_search", "browse_url", "read_file", "write_file", "list_files", "execute_code"],
  backend: ["web_search", "browse_url", "read_file", "write_file", "list_files", "execute_code"],
  security: ["web_search", "browse_url", "read_file", "list_files", "gmail_get_inbox"],
  marketing: ["web_search", "browse_url", "read_file", "list_files", "slack_send_message", "slack_get_unread_mentions", "gmail_get_inbox", "gmail_draft_email"],
  content: ["web_search", "browse_url", "read_file", "write_file", "list_files", "gmail_draft_email"],
};

interface Metrics {
  cost_usd: number;
  latency_ms: number;
}

export interface JarvisStore {
  // --- Connection ---
  connection: ConnectionStatus;
  setConnection: (status: ConnectionStatus) => void;

  // --- Voice / orb ---
  voiceState: VoiceState;
  audioLevel: number; // 0..1 amplitude for orb reactivity
  setVoiceState: (state: VoiceState) => void;
  setAudioLevel: (level: number) => void;

  // --- Agents ---
  agents: AgentState[];
  applyAgentUpdate: (u: {
    agent_id: string;
    agent_name: string;
    status: AgentStatus;
    current_task: string | null;
  }) => void;

  // --- Reasoning: tokens, tool calls, model, metrics ---
  model: string;
  streamingText: string;
  toolCalls: ToolCallRecord[];
  metrics: Metrics;
  appendToken: (content: string, model: string, isFinal: boolean) => void;
  clearStream: () => void;
  applyToolCall: (c: {
    tool_name: string;
    agent_id: string;
    args: Record<string, unknown>;
    result: unknown | null;
    timestamp: string;
  }) => void;
  setMetrics: (m: Partial<Metrics> & { model?: string }) => void;

  // --- Communications ---
  slackMessages: SlackMessage[];
  gmailMessages: GmailMessage[];
  setSlackMessages: (m: SlackMessage[]) => void;
  setGmailMessages: (m: GmailMessage[]) => void;

  // --- Tools matrix ---
  tools: string[];
  permissions: Record<string, string[]>;
  setPermissions: (p: Record<string, string[]>, tools?: string[]) => void;
  toggleToolPermission: (agentId: string, tool: string) => void;
}

export const useStore = create<JarvisStore>((set) => ({
  connection: "connecting",
  setConnection: (status) => set({ connection: status }),

  voiceState: "idle",
  audioLevel: 0,
  setVoiceState: (voiceState) => set({ voiceState }),
  setAudioLevel: (audioLevel) => set({ audioLevel }),

  agents: INITIAL_AGENTS,
  applyAgentUpdate: (u) =>
    set((s) => {
      const agents = s.agents.map((a) =>
        a.agent_id === u.agent_id
          ? {
              ...a,
              agent_name: u.agent_name || a.agent_name,
              status: u.status,
              current_task: u.current_task,
              history:
                u.current_task && u.current_task !== a.current_task
                  ? [u.current_task, ...a.history].slice(0, 20)
                  : a.history,
            }
          : a,
      );
      // Unknown agent id → append it so the window still reflects reality.
      if (!agents.some((a) => a.agent_id === u.agent_id)) {
        agents.push({
          agent_id: u.agent_id,
          agent_name: u.agent_name,
          role: u.agent_id,
          status: u.status,
          current_task: u.current_task,
          history: u.current_task ? [u.current_task] : [],
        });
      }
      return { agents };
    }),

  model: "Claude Opus 4.7",
  streamingText: "",
  toolCalls: [],
  metrics: { cost_usd: 0, latency_ms: 0 },
  appendToken: (content, model, isFinal) =>
    set((s) => ({
      model: model || s.model,
      streamingText: isFinal ? s.streamingText : s.streamingText + content,
    })),
  clearStream: () => set({ streamingText: "" }),
  applyToolCall: (c) =>
    set((s) => {
      const id = `${c.tool_name}-${c.agent_id}-${c.timestamp}`;
      const existing = s.toolCalls.findIndex((t) => t.id === id);
      const record: ToolCallRecord = { id, ...c };
      if (existing >= 0) {
        // Result follow-up for an in-flight call: replace in place.
        const next = s.toolCalls.slice();
        next[existing] = record;
        return { toolCalls: next };
      }
      return { toolCalls: [record, ...s.toolCalls].slice(0, 30) };
    }),
  setMetrics: (m) =>
    set((s) => ({
      model: m.model || s.model,
      metrics: {
        cost_usd: m.cost_usd ?? s.metrics.cost_usd,
        latency_ms: m.latency_ms ?? s.metrics.latency_ms,
      },
    })),

  slackMessages: [],
  gmailMessages: [],
  setSlackMessages: (slackMessages) => set({ slackMessages }),
  setGmailMessages: (gmailMessages) => set({ gmailMessages }),

  tools: ALL_TOOLS,
  permissions: INITIAL_PERMISSIONS,
  setPermissions: (permissions, tools) =>
    set((s) => ({ permissions, tools: tools ?? s.tools })),
  toggleToolPermission: (agentId, tool) =>
    set((s) => {
      const current = s.permissions[agentId] ?? [];
      const has = current.includes(tool);
      const next = has
        ? current.filter((t) => t !== tool)
        : [...current, tool];
      return { permissions: { ...s.permissions, [agentId]: next } };
    }),
}));
