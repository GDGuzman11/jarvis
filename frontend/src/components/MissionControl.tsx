/**
 * MissionControl — the prominent header panel of the AgentsWindow for handing
 * high-level goals to Atlas (the Production Lead). Atlas classifies the goal and
 * delegates to the right specialist agent automatically, so this is the "just
 * tell Jarvis what you want done" entry point.
 *
 * Submits to the same direct-task endpoint as the per-card inputs, targeting the
 * `production_lead` agent (slug `atlas`). Local state only — no store coupling.
 */

import { useState, type KeyboardEvent } from "react";
import { submitAgentTask } from "../lib/api";

/** Internal agent_id for Atlas; mapped to slug `atlas` inside submitAgentTask. */
const ATLAS_ID = "production_lead";

export function MissionControl() {
  const [goal, setGoal] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);

  async function handleSend() {
    const text = goal.trim();
    if (!text || sending) return;
    setSending(true);
    setError(null);
    setConfirmed(false);
    try {
      await submitAgentTask(ATLAS_ID, text);
      setGoal("");
      setConfirmed(true);
      setTimeout(() => setConfirmed(false), 3000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to dispatch goal.");
    } finally {
      setSending(false);
    }
  }

  function handleKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") handleSend();
  }

  return (
    <div className="glass hud-corners mb-3 p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold uppercase tracking-[0.3em] text-glow-cyan">
          Mission Control
        </h3>
        <span className="text-[10px] uppercase tracking-widest text-jarvis-muted">
          Task Atlas
        </span>
      </div>
      <p className="mt-1 text-[11px] text-jarvis-muted">
        Hand a high-level goal to Atlas — it breaks the work down and delegates.
      </p>
      <div className="mt-2 flex gap-2">
        <input
          type="text"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          onKeyDown={handleKey}
          disabled={sending}
          placeholder="e.g. Plan and ship the new onboarding flow…"
          className="min-w-0 flex-1 border border-jarvis-cyan/30 bg-jarvis-bg/60 px-3 py-2 text-sm text-jarvis-text placeholder:text-jarvis-muted/50 outline-none transition-colors focus:border-jarvis-cyan/70 disabled:opacity-40"
        />
        <button
          type="button"
          onClick={handleSend}
          disabled={sending || !goal.trim()}
          className="hud-btn shrink-0 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {sending ? "DISPATCHING…" : "DISPATCH"}
        </button>
      </div>
      {error && <p className="mt-1 text-[10px] text-jarvis-red">{error}</p>}
      {confirmed && (
        <p className="mt-1 text-[10px] text-emerald-400">Goal dispatched to Atlas.</p>
      )}
    </div>
  );
}

export default MissionControl;
