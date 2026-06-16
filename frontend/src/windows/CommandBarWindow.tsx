/**
 * Window 7 — CommandBarWindow. An always-on-top bar docked bottom-centre with
 * the five hub verbs (PLAN · EXECUTE · MONITOR · LEARN · ADAPT) plus a compact
 * system-overview readout. Each verb raises/focuses the most relevant window
 * and emits a forward-looking `command` event over the WebSocket so the backend
 * can wire behaviour later. LEARN is disabled until the Memory window (16F) ships.
 */

import type { MouseEvent } from "react";
import { useStore } from "../lib/store";
import { sendCommand } from "../lib/websocket";

interface Verb {
  verb: string;
  target: string | null; // window label to focus, or null if not built yet
  disabled?: boolean;
  hint: string;
}

const VERBS: Verb[] = [
  { verb: "PLAN", target: "agents", hint: "Mission control & agents" },
  { verb: "EXECUTE", target: "reasoning", hint: "Reasoning & chat" },
  { verb: "MONITOR", target: "agents", hint: "Agent status" },
  { verb: "LEARN", target: "memory", disabled: true, hint: "Memory graph — coming in 16F" },
  { verb: "ADAPT", target: "tools", hint: "Tool permissions" },
];

/** Raise/focus another Tauri window by label. No-op in plain-browser dev. */
async function focusWindow(label: string) {
  try {
    const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
    const win = await WebviewWindow.getByLabel(label);
    if (win) {
      await win.unminimize().catch(() => {});
      await win.setFocus();
    }
  } catch {
    // Browser mode — multi-window focus not available.
  }
}

async function startDrag(e: MouseEvent) {
  if (e.button !== 0) return;
  try {
    const { getCurrentWebviewWindow } = await import("@tauri-apps/api/webviewWindow");
    await getCurrentWebviewWindow().startDragging();
  } catch {
    // Browser mode — dragging not available.
  }
}

function onVerb(v: Verb) {
  if (v.disabled) return;
  sendCommand({ action: "command", verb: v.verb });
  if (v.target) void focusWindow(v.target);
}

export function CommandBarWindow() {
  const connection = useStore((s) => s.connection);
  const model = useStore((s) => s.model);
  const agents = useStore((s) => s.agents);
  const sessionCostUsd = useStore((s) => s.sessionCostUsd);

  const online = agents.filter((a) => a.status !== "offline").length;
  const connColor =
    connection === "open"
      ? "text-jarvis-accent"
      : connection === "closed"
        ? "text-jarvis-red"
        : "text-jarvis-gold";
  const connLabel =
    connection === "open" ? "ONLINE" : connection === "closed" ? "OFFLINE" : "LINKING";

  return (
    <div className="glass hud-corners relative flex h-screen w-screen flex-col overflow-hidden">
      <div className="data-stream-top absolute inset-x-0 top-0 h-0 w-full" />

      {/* Verb row */}
      <div className="flex flex-1 items-center justify-center gap-1.5 px-3 pt-2">
        {VERBS.map((v) => (
          <button
            key={v.verb}
            type="button"
            title={v.hint}
            disabled={v.disabled}
            onClick={() => onVerb(v)}
            className="hud-btn flex-1"
          >
            {v.verb}
          </button>
        ))}
      </div>

      {/* System overview strip — doubles as the drag handle. */}
      <div
        onMouseDown={startDrag}
        title="Drag to move"
        className="flex cursor-grab select-none items-center justify-center gap-3 px-3 pb-1.5 pt-1 text-[9px] uppercase tracking-widest active:cursor-grabbing"
      >
        <span className="truncate text-jarvis-cyan/80">{model}</span>
        <span className="text-jarvis-muted">·</span>
        <span className="text-jarvis-muted">
          AGENTS <span className="text-jarvis-cyan">{online}/{agents.length}</span>
        </span>
        <span className="text-jarvis-muted">·</span>
        <span className={connColor}>{connLabel}</span>
        <span className="text-jarvis-muted">·</span>
        <span className="text-jarvis-muted">
          SESSION <span className="font-mono text-jarvis-gold">${sessionCostUsd.toFixed(2)}</span>
        </span>
      </div>
    </div>
  );
}

export default CommandBarWindow;
