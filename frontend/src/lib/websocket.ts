/**
 * WebSocket singleton — the one connection every window opens to the backend
 * hub at ws://127.0.0.1:8000/ws. Incoming events are decoded and dispatched
 * into the Zustand store. Reconnects automatically with capped backoff.
 *
 * Each Tauri window runs its own renderer process, so each window creates its
 * own singleton instance — that's intentional and matches the backend hub,
 * which fans the same broadcast out to every connection.
 */

import { useStore } from "./store";
import type { JarvisEvent } from "./types";

const WS_URL = "ws://127.0.0.1:8000/ws";
const MAX_BACKOFF_MS = 10_000;
const BASE_BACKOFF_MS = 500;

let socket: WebSocket | null = null;
let reconnectAttempts = 0;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let started = false;

function dispatch(event: JarvisEvent): void {
  const s = useStore.getState();
  switch (event.type) {
    case "agent_update":
      s.applyAgentUpdate({
        agent_id: event.agent_id,
        agent_name: event.agent_name,
        status: event.status,
        current_task: event.current_task,
      });
      break;
    case "token":
      s.appendToken(event.content, event.model, event.is_final);
      s.appendJarvisToken(event.content, event.is_final);
      break;
    case "tool_call":
      s.applyToolCall({
        tool_name: event.tool_name,
        agent_id: event.agent_id,
        args: event.args,
        result: event.result,
        timestamp: event.timestamp,
      });
      break;
    case "voice_state":
      s.setVoiceState(event.state);
      break;
    case "audio_level":
      s.setAudioLevel(event.level);
      break;
    case "metrics":
      s.setMetrics({
        cost_usd: event.cost_usd,
        latency_ms: event.latency_ms,
        model: event.model,
        input_tokens: event.input_tokens,
        output_tokens: event.output_tokens,
        cache_read_tokens: event.cache_read_tokens,
        cache_write_tokens: event.cache_write_tokens,
      });
      break;
    case "comms":
      if (event.slack) s.setSlackMessages(event.slack);
      if (event.gmail) s.setGmailMessages(event.gmail);
      break;
    case "tool_permissions":
      s.setPermissions(event.permissions, event.tools);
      break;
    case "shutdown":
      disconnectWebSocket();
      // Close the Tauri window; fall back to window.close() in browser mode.
      setTimeout(async () => {
        try {
          const { getCurrentWebviewWindow } = await import(
            "@tauri-apps/api/webviewWindow"
          );
          await getCurrentWebviewWindow().close();
        } catch {
          window.close();
        }
      }, 300);
      break;
    default:
      // Unknown event type — ignore rather than crash a window.
      break;
  }
}

function scheduleReconnect(): void {
  if (reconnectTimer) return;
  const delay = Math.min(
    BASE_BACKOFF_MS * 2 ** reconnectAttempts,
    MAX_BACKOFF_MS,
  );
  reconnectAttempts += 1;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    open();
  }, delay);
}

function open(): void {
  useStore.getState().setConnection("connecting");
  try {
    socket = new WebSocket(WS_URL);
  } catch {
    scheduleReconnect();
    return;
  }

  socket.onopen = () => {
    reconnectAttempts = 0;
    useStore.getState().setConnection("open");
  };

  socket.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data as string) as JarvisEvent;
      dispatch(data);
    } catch {
      // Malformed frame — drop it silently.
    }
  };

  socket.onclose = () => {
    useStore.getState().setConnection("closed");
    socket = null;
    scheduleReconnect();
  };

  socket.onerror = () => {
    // onerror is always followed by onclose; let onclose handle reconnect.
    socket?.close();
  };
}

/** Connect once (idempotent). Call from each window root on mount. */
export function connectWebSocket(): void {
  if (started) return;
  started = true;
  open();
}

/**
 * Send a JSON command back to the backend over the same socket. The backend
 * currently drains inbound frames (forward-compatible); this is how the Tools
 * window requests a permission grant/revoke. No-ops if the socket is not open.
 */
export function sendCommand(command: Record<string, unknown>): boolean {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(command));
    return true;
  }
  return false;
}

/** Close the connection and stop reconnecting (used on teardown/tests). */
export function disconnectWebSocket(): void {
  started = false;
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  socket?.close();
  socket = null;
}
