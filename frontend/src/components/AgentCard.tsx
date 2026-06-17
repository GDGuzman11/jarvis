/**
 * AgentCard — one agent's live status card. Clickable to expand the task
 * history. All data is passed in from the store; this component is presentation
 * only.
 */

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { AgentState } from "../lib/types";
import { useStore } from "../lib/store";
import { renameAgent } from "../lib/api";
import StatusBadge from "./StatusBadge";
import AgentTaskPanel from "./AgentTaskPanel";

export function AgentCard({ agent }: { agent: AgentState }) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(agent.agent_name);
  const updateAgentName = useStore((s) => s.updateAgentName);

  const commitRename = () => {
    const name = draft.trim();
    setEditing(false);
    if (!name || name === agent.agent_name) return;
    // Optimistically update the store, then fire the REST call.
    updateAgentName(agent.agent_id, name);
    void renameAgent(agent.agent_id, name);
  };

  const startEdit = () => {
    setDraft(agent.agent_name);
    setEditing(true);
  };

  return (
    <motion.div
      layout
      onClick={() => !editing && setExpanded((e) => !e)}
      className="glass glass-hover cursor-pointer p-4"
      whileHover={{ y: -2 }}
    >
      <div className="flex items-start justify-between">
        <div className="min-w-0 flex-1">
          {editing ? (
            <div
              className="flex items-center gap-1.5"
              onClick={(e) => e.stopPropagation()}
            >
              <input
                autoFocus
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commitRename();
                  if (e.key === "Escape") setEditing(false);
                }}
                className="w-full min-w-0 border-b border-helix-gold/40 bg-transparent text-lg font-bold tracking-wide text-glow-gold outline-none"
              />
              <button
                type="button"
                aria-label="Confirm name"
                onClick={commitRename}
                className="shrink-0 px-1 text-helix-gold hover:text-glow-gold"
              >
                ✓
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <h3 className="truncate text-lg font-bold tracking-wide text-glow-gold">
                {agent.agent_name}
              </h3>
              <button
                type="button"
                aria-label="Edit name"
                onClick={(e) => {
                  e.stopPropagation();
                  startEdit();
                }}
                className="shrink-0 text-xs text-helix-muted hover:text-helix-gold"
              >
                ✎
              </button>
            </div>
          )}
          <p className="text-xs uppercase tracking-widest text-helix-muted">{agent.role}</p>
        </div>
        <StatusBadge status={agent.status} />
      </div>

      <div className="mt-3 border-t border-helix-gold/10 pt-2">
        <p className="text-[10px] uppercase tracking-widest text-helix-muted">Current Task</p>
        <p className="mt-0.5 truncate text-sm text-helix-ink">
          {agent.current_task ?? "— awaiting assignment —"}
        </p>
      </div>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="mt-3 border-t border-helix-gold/10 pt-2">
              <p className="text-[10px] uppercase tracking-widest text-helix-muted">Task History</p>
              {agent.history.length === 0 ? (
                <p className="mt-1 text-xs italic text-helix-muted">No history yet.</p>
              ) : (
                <ul className="mt-1 space-y-1">
                  {agent.history.map((task, i) => (
                    <li key={i} className="flex gap-2 text-xs text-helix-ink/80">
                      <span className="text-helix-gold">▸</span>
                      <span className="truncate">{task}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Phase 13A — direct task input + per-agent task log. */}
      <AgentTaskPanel agentId={agent.agent_id} />

      <p className="mt-2 text-right text-[10px] tracking-widest text-helix-muted">
        {expanded ? "▲ COLLAPSE" : "▼ EXPAND"}
      </p>
    </motion.div>
  );
}

export default AgentCard;
