/**
 * StatusBadge — small glowing pill for agent status.
 * idle=blue, working=gold, error=red, offline=gray.
 */

import type { AgentStatus } from "../lib/types";

const STATUS_STYLE: Record<AgentStatus, { dot: string; text: string; label: string }> = {
  idle: { dot: "bg-jarvis-cyan", text: "text-jarvis-cyan", label: "IDLE" },
  working: { dot: "bg-jarvis-gold", text: "text-jarvis-gold", label: "WORKING" },
  error: { dot: "bg-jarvis-red", text: "text-jarvis-red", label: "ERROR" },
  offline: { dot: "bg-jarvis-gray", text: "text-jarvis-muted", label: "OFFLINE" },
};

export function StatusBadge({ status }: { status: AgentStatus }) {
  const s = STATUS_STYLE[status];
  return (
    <span className={`inline-flex items-center gap-1.5 text-[11px] font-semibold tracking-widest ${s.text}`}>
      <span className={`h-2 w-2 ${s.dot} ${status === "working" ? "animate-pulse-glow" : ""}`} style={{ boxShadow: "0 0 8px currentColor" }} />
      {s.label}
    </span>
  );
}

export default StatusBadge;
