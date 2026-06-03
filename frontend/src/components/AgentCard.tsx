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
                className="w-full min-w-0 border-b border-jarvis-cyan/40 bg-transparent text-lg font-bold tracking-wide text-glow-cyan outline-none"
              />
              <button
                type="button"
                aria-label="Confirm name"
                onClick={commitRename}
                className="shrink-0 px-1 text-jarvis-cyan hover:text-glow-cyan"
              >
                ✓
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <h3 className="truncate text-lg font-bold tracking-wide text-glow-cyan">
                {agent.agent_name}
              </h3>
              <button
                type="button"
                aria-label="Edit name"
                onClick={(e) => {
                  e.stopPropagation();
                  startEdit();
                }}
                className="shrink-0 text-xs text-jarvis-muted hover:text-jarvis-cyan"
              >
                ✎
              </button>
            </div>
          )}
          <p className="text-xs uppercase tracking-widest text-jarvis-muted">{agent.role}</p>
        </div>
        <StatusBadge status={agent.status} />
      </div>

      <div className="mt-3 border-t border-jarvis-cyan/10 pt-2">
        <p className="text-[10px] uppercase tracking-widest text-jarvis-muted">Current Task</p>
        <p className="mt-0.5 truncate text-sm text-jarvis-text">
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
            <div className="mt-3 border-t border-jarvis-cyan/10 pt-2">
              <p className="text-[10px] uppercase tracking-widest text-jarvis-muted">Task History</p>
              {agent.history.length === 0 ? (
                <p className="mt-1 text-xs italic text-jarvis-muted">No history yet.</p>
              ) : (
                <ul className="mt-1 space-y-1">
                  {agent.history.map((task, i) => (
                    <li key={i} className="flex gap-2 text-xs text-jarvis-text/80">
                      <span className="text-jarvis-cyan">▸</span>
                      <span className="truncate">{task}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <p className="mt-2 text-right text-[10px] tracking-widest text-jarvis-muted">
        {expanded ? "▲ COLLAPSE" : "▼ EXPAND"}
      </p>
    </motion.div>
  );
}

export default AgentCard;
