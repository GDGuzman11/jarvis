/**
 * ToolCard — a single tool/agent matrix cell rendered as a glowing checkbox.
 * Toggling optimistically updates the store and notifies the backend over the
 * WebSocket command channel (with a REST fallback).
 */

import { setToolPermission } from "../lib/api";
import { useStore } from "../lib/store";
import { sendCommand } from "../lib/websocket";

interface ToolCardProps {
  agentId: string;
  tool: string;
}

export function ToolCard({ agentId, tool }: ToolCardProps) {
  const allowed = useStore((s) => s.permissions[agentId]?.includes(tool) ?? false);
  const toggle = useStore((s) => s.toggleToolPermission);

  const onClick = () => {
    const nextAllow = !allowed;
    toggle(agentId, tool); // optimistic
    // Notify backend; WebSocket first, REST as a fallback.
    const sent = sendCommand({
      type: "set_tool_permission",
      agent_id: agentId,
      tool,
      allow: nextAllow,
    });
    if (!sent) void setToolPermission(agentId, tool, nextAllow);
  };

  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={allowed}
      aria-label={`${allowed ? "Revoke" : "Grant"} ${tool} for ${agentId}`}
      className={`flex h-7 w-7 items-center justify-center border transition-all ${
        allowed
          ? "border-jarvis-cyan bg-jarvis-cyan/20 text-jarvis-cyan"
          : "border-jarvis-gray/40 bg-transparent text-transparent hover:border-jarvis-cyan/60"
      }`}
      style={allowed ? { boxShadow: "0 0 10px rgba(255,194,71,0.5)" } : undefined}
    >
      {allowed ? "✓" : ""}
    </button>
  );
}

export default ToolCard;
