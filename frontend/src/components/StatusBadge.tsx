/**
 * StatusBadge — small glowing pill for agent status.
 * idle=gold, working=aqua accent (live, pulsing), error=amber alert (pulsing), offline=muted.
 */

import type { AgentStatus } from "../lib/types";

const STATUS_STYLE: Record<AgentStatus, { dot: string; text: string; label: string }> = {
  idle: { dot: "bg-jarvis-cyan", text: "text-jarvis-cyan", label: "IDLE" },
  working: { dot: "bg-jarvis-accent", text: "text-jarvis-accent", label: "WORKING" },
  error: { dot: "bg-jarvis-red", text: "text-jarvis-red", label: "ERROR" },
  offline: { dot: "bg-jarvis-gray", text: "text-jarvis-muted", label: "OFFLINE" },
};

export function StatusBadge({ status }: { status: AgentStatus }) {
  const s = STATUS_STYLE[status];
  const pulse = status === "working" || status === "error";
  return (
    <span className={`inline-flex items-center gap-1.5 text-[11px] font-semibold tracking-widest ${s.text}`}>
      <span className={`h-2 w-2 ${s.dot} ${pulse ? "animate-pulse-glow" : ""}`} style={{ boxShadow: "0 0 8px currentColor" }} />
      {s.label}
    </span>
  );
}

export default StatusBadge;
