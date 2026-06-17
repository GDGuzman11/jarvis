/**
 * AgentTaskPanel — the Phase 13A interactive footer on each AgentCard. It adds
 * two things on top of the read-only card: a text input + SEND button that
 * queues a task directly to this agent (`POST /api/agents/{slug}/task`), and an
 * expandable task log fetched from `GET /api/agents/{slug}/tasks`.
 *
 * Presentation + local interaction only — it never touches the WebSocket store,
 * so the live `agent_update` stream that drives the card above keeps flowing.
 */

import { useState, useEffect, useCallback, type KeyboardEvent } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { submitAgentTask, fetchAgentTasks, type AgentTask } from "../lib/api";

/** queued=cyan, running=gold, done=green, failed=red. */
const STATUS_COLOR: Record<string, string> = {
  queued: "text-helix-gold border-helix-gold/40",
  running: "text-helix-gold-bright border-helix-gold-bright/40",
  in_progress: "text-helix-gold-bright border-helix-gold-bright/40",
  done: "text-emerald-400 border-emerald-400/40",
  completed: "text-emerald-400 border-emerald-400/40",
  failed: "text-helix-alert border-helix-alert/40",
  error: "text-helix-alert border-helix-alert/40",
};

function StatusPill({ status }: { status: string }) {
  const cls = STATUS_COLOR[status] ?? "text-helix-muted border-helix-muted/40";
  return (
    <span className={`shrink-0 border px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-widest ${cls}`}>
      {status}
    </span>
  );
}

export function AgentTaskPanel({ agentId }: { agentId: string }) {
  const [goal, setGoal] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [logOpen, setLogOpen] = useState(false);
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [loadingLog, setLoadingLog] = useState(false);

  const loadTasks = useCallback(async () => {
    setLoadingLog(true);
    setTasks(await fetchAgentTasks(agentId));
    setLoadingLog(false);
  }, [agentId]);

  // Fetch the log once on mount so the count badge is meaningful before expand.
  useEffect(() => {
    void loadTasks();
  }, [loadTasks]);

  async function handleSend() {
    const text = goal.trim();
    if (!text || sending) return;
    setSending(true);
    setError(null);
    try {
      await submitAgentTask(agentId, text);
      setGoal("");
      await loadTasks(); // refresh the log so the new task appears immediately
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to queue task.");
    } finally {
      setSending(false);
    }
  }

  function handleKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") handleSend();
  }

  return (
    <div className="mt-3 border-t border-helix-gold/10 pt-2" onClick={(e) => e.stopPropagation()}>
      <p className="text-[10px] uppercase tracking-widest text-helix-muted">Assign Task</p>
      <div className="mt-1 flex gap-2">
        <input
          type="text"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          onKeyDown={handleKey}
          disabled={sending}
          placeholder="Describe a task…"
          className="min-w-0 flex-1 border border-helix-gold/30 bg-helix-bg/60 px-2 py-1.5 text-xs text-helix-ink placeholder:text-helix-muted/50 outline-none transition-colors focus:border-helix-gold/70 disabled:opacity-40"
        />
        <button
          type="button"
          onClick={handleSend}
          disabled={sending || !goal.trim()}
          className="hud-btn shrink-0 px-3 py-1.5 text-xs disabled:cursor-not-allowed disabled:opacity-40"
        >
          {sending ? "…" : "SEND"}
        </button>
      </div>
      {error && <p className="mt-1 text-[10px] text-helix-alert">{error}</p>}

      <button
        type="button"
        onClick={() => setLogOpen((o) => !o)}
        className="mt-2 flex w-full items-center gap-1 text-[10px] uppercase tracking-widest text-helix-muted hover:text-helix-gold"
      >
        <span className="text-helix-gold">{logOpen ? "▾" : "▸"}</span>
        Task Log
        <span className="text-helix-muted/70">({tasks.length})</span>
      </button>

      <AnimatePresence initial={false}>
        {logOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <ul className="mt-1 space-y-1">
              {loadingLog ? (
                <li className="text-[11px] italic text-helix-muted">Loading…</li>
              ) : tasks.length === 0 ? (
                <li className="text-[11px] italic text-helix-muted">No tasks yet.</li>
              ) : (
                tasks.map((t) => (
                  <li key={t.task_id} className="flex items-center justify-between gap-2 text-[11px] text-helix-ink/80">
                    <span className="truncate" title={t.goal}>
                      {t.goal.length > 60 ? `${t.goal.slice(0, 60)}…` : t.goal}
                    </span>
                    <StatusPill status={t.status} />
                  </li>
                ))
              )}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default AgentTaskPanel;
