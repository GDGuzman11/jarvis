/**
 * AgentCard — one agent's live status card. Clickable to expand the task
 * history. All data is passed in from the store; this component is presentation
 * only.
 */

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { AgentState } from "../lib/types";
import StatusBadge from "./StatusBadge";

export function AgentCard({ agent }: { agent: AgentState }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <motion.div
      layout
      onClick={() => setExpanded((e) => !e)}
      className="glass glass-hover cursor-pointer p-4"
      whileHover={{ y: -2 }}
    >
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-lg font-bold tracking-wide text-glow-cyan">{agent.agent_name}</h3>
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
