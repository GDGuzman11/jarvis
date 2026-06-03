/**
 * Thin HTTP helpers for the backend REST surface (currently `/health`, plus a
 * forward-declared tool-permission endpoint). The Tools window prefers the
 * WebSocket command channel (`sendCommand`) but falls back to this REST call so
 * the toggle still works once the backend exposes the route.
 */

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
