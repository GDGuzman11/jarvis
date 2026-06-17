/**
 * Thin HTTP helpers for the backend REST surface (currently `/health`, plus a
 * forward-declared tool-permission endpoint). The Tools window prefers the
 * WebSocket command channel (`sendCommand`) but falls back to this REST call so
 * the toggle still works once the backend exposes the route.
 */

import type { MemoryGraph } from "./types";

const API_BASE = "http://127.0.0.1:8000";

export async function fetchHealth(): Promise<{ status: string; version: string } | null> {
  try {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) return null;
    return (await res.json()) as { status: string; version: string };
  } catch {
    return null;
  }
}

/**
 * Request a tool-permission change. Resolves true on a 2xx, false otherwise
 * (including when the endpoint does not yet exist). Callers should optimistically
 * update local state and treat false as "backend will catch up via WebSocket".
 */
export async function setToolPermission(
  agentId: string,
  tool: string,
  allow: boolean,
): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/tools/permissions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent_id: agentId, tool, allow }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/** Per-credential completion map returned by `/setup/status`. */
export interface SetupStatus {
  /** credential key -> whether it is already stored in the keyring. */
  credentials: Record<string, boolean>;
  complete: boolean;
}

/** The credential keys the first-run wizard collects, in display order. */
export const SETUP_CREDENTIALS: { key: string; label: string }[] = [
  { key: "anthropic_api_key", label: "Anthropic API Key" },
  { key: "elevenlabs_api_key", label: "ElevenLabs API Key" },
  { key: "elevenlabs_voice_id", label: "ElevenLabs Voice ID" },
  { key: "slack_bot_token", label: "Slack Bot Token" },
  { key: "gmail_client_id", label: "Gmail Client ID" },
  { key: "gmail_client_secret", label: "Gmail Client Secret" },
  { key: "gmail_refresh_token", label: "Gmail Refresh Token" },
];

/** GET `/setup/status` — which credentials are already stored. */
export async function fetchSetupStatus(): Promise<SetupStatus | null> {
  try {
    const res = await fetch(`${API_BASE}/setup/status`);
    if (!res.ok) return null;
    return (await res.json()) as SetupStatus;
  } catch {
    return null;
  }
}

/** GET `/setup/complete` — true once every required credential is stored. */
export async function fetchSetupComplete(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/setup/complete`);
    if (!res.ok) return false;
    const data = (await res.json()) as { complete: boolean };
    return Boolean(data.complete);
  } catch {
    return false;
  }
}

/** POST `/setup/credential` — store a single credential in the keyring. */
export async function saveSetupCredential(
  key: string,
  value: string,
): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/setup/credential`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, value }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * Rename an agent. POSTs to `/api/agents/{agent_id}/rename` with `{ name }`.
 * Resolves true on a 2xx, false otherwise (including when the route does not yet
 * exist). The caller optimistically updates the store regardless.
 */
export async function renameAgent(
  agentId: string,
  name: string,
): Promise<boolean> {
  try {
    const res = await fetch(
      `${API_BASE}/api/agents/${encodeURIComponent(agentId)}/rename`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      },
    );
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * Maps the store's internal agent_id (e.g. `production_lead`) to the public
 * display slug the task endpoints expect (e.g. `atlas`). Mirrors the backend
 * `_PUBLIC_TO_AGENT_ID` table in `backend/main.py`. The agent's display name is
 * user-editable, so we key off the stable internal id, never the name.
 */
export const AGENT_ID_TO_SLUG: Record<string, string> = {
  production_lead: "atlas",
  frontend: "ben",
  backend: "kado",
  security: "sentinel",
  marketing: "vega",
  content: "quill",
};

/** A single task row as returned by `GET /api/agents/{agent_id}/tasks`. */
export interface AgentTask {
  task_id: number | string;
  goal: string;
  status: string;
  created_at: string;
}

/**
 * Submit a goal directly to one agent. POSTs to `/api/agents/{slug}/task` with
 * `{ goal }`. Resolves the new task_id on success, or throws an Error whose
 * message is the backend `detail` (e.g. "goal must not be empty") so the UI can
 * surface it inline.
 */
export async function submitAgentTask(
  agentId: string,
  goal: string,
): Promise<{ task_id: number | string; status: string }> {
  const slug = AGENT_ID_TO_SLUG[agentId] ?? agentId;
  let res: Response;
  try {
    res = await fetch(
      `${API_BASE}/api/agents/${encodeURIComponent(slug)}/task`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal }),
      },
    );
  } catch {
    throw new Error("Backend offline.");
  }
  if (!res.ok) {
    const data = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(data.detail ?? `Request failed (${res.status}).`);
  }
  return (await res.json()) as { task_id: number | string; status: string };
}

/**
 * GET `/api/memory/graph` — the full memory brain snapshot (nodes + edges).
 * Returns null on any error (offline backend, route missing, malformed body)
 * so the Memory window can degrade to its "memory still forming" empty state.
 */
export async function fetchMemoryGraph(): Promise<MemoryGraph | null> {
  try {
    const res = await fetch(`${API_BASE}/api/memory/graph`);
    if (!res.ok) return null;
    const data = (await res.json()) as Partial<MemoryGraph>;
    return {
      nodes: Array.isArray(data.nodes) ? data.nodes : [],
      edges: Array.isArray(data.edges) ? data.edges : [],
    };
  } catch {
    return null;
  }
}

/**
 * Fetch the most recent tasks for one agent (newest first, max 5). Returns an
 * empty array on any error so the caller can render an empty log gracefully.
 */
export async function fetchAgentTasks(agentId: string): Promise<AgentTask[]> {
  const slug = AGENT_ID_TO_SLUG[agentId] ?? agentId;
  try {
    const res = await fetch(
      `${API_BASE}/api/agents/${encodeURIComponent(slug)}/tasks`,
    );
    if (!res.ok) return [];
    const data = (await res.json()) as { tasks?: AgentTask[] };
    return data.tasks ?? [];
  } catch {
    return [];
  }
}
