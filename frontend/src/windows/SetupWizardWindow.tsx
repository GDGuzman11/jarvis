/**
 * First-run Setup Wizard — collects the API credentials Jarvis needs and stores
 * each in the Windows Credential Manager (via the backend keyring). On mount it
 * checks `/setup/status`; if setup is already complete it shows the launch state
 * immediately. Each filled field is POSTed to `/setup/credential`; a progress
 * indicator tracks which creds are saved. The "Launch Jarvis" button appears
 * once `/setup/complete` returns true.
 *
 * Credential values are entered into masked (password) inputs and never logged
 * or persisted on the frontend — they go straight to the keyring.
 */

import { useEffect, useState } from "react";
import {
  SETUP_CREDENTIALS,
  fetchSetupComplete,
  fetchSetupStatus,
  saveSetupCredential,
} from "../lib/api";
import WindowFrame from "../components/WindowFrame";

export function SetupWizardWindow() {
  const [saved, setSaved] = useState<Record<string, boolean>>({});
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [complete, setComplete] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const status = await fetchSetupStatus();
      if (cancelled) return;
      if (status) {
        setSaved(status.credentials ?? {});
        setComplete(status.complete);
      }
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const savedCount = SETUP_CREDENTIALS.filter((c) => saved[c.key]).length;
  const total = SETUP_CREDENTIALS.length;

  const handleSave = async (key: string) => {
    const value = (drafts[key] ?? "").trim();
    if (!value) return;
    setBusy(key);
    const ok = await saveSetupCredential(key, value);
    if (ok) {
      setSaved((s) => ({ ...s, [key]: true }));
      setDrafts((d) => ({ ...d, [key]: "" }));
      setComplete(await fetchSetupComplete());
    }
    setBusy(null);
  };

  const handleLaunch = () => {
    // In Tauri the launcher closes this window; in a browser preview just hide.
    window.close();
  };

  return (
    <WindowFrame title="Setup" index={0}>
      <div className="hud-scroll h-full overflow-y-auto p-6">
        {loading ? (
          <p className="text-sm text-jarvis-muted">Checking setup status…</p>
        ) : (
          <>
            <div className="mb-4">
              <p className="text-xs uppercase tracking-widest text-jarvis-muted">
                Credentials saved
              </p>
              <p className="text-2xl font-bold text-glow-cyan">
                {savedCount}
                <span className="text-jarvis-muted"> / {total}</span>
              </p>
              <div className="mt-2 h-1 w-full bg-jarvis-cyan/10">
                <div
                  className="h-1 bg-jarvis-cyan transition-all"
                  style={{ width: `${(savedCount / total) * 100}%` }}
                />
              </div>
            </div>

            <div className="space-y-3">
              {SETUP_CREDENTIALS.map(({ key, label }) => {
                const isSaved = saved[key];
                return (
                  <div key={key} className="glass p-3">
                    <div className="flex items-center justify-between">
                      <label className="text-xs uppercase tracking-widest text-jarvis-muted">
                        {label}
                      </label>
                      {isSaved && (
                        <span className="text-[10px] font-semibold tracking-widest text-jarvis-cyan">
                          ✓ SAVED
                        </span>
                      )}
                    </div>
                    <div className="mt-2 flex gap-2">
                      <input
                        type="password"
                        autoComplete="off"
                        placeholder={isSaved ? "•••••••• (stored)" : "Enter value"}
                        value={drafts[key] ?? ""}
                        onChange={(e) =>
                          setDrafts((d) => ({ ...d, [key]: e.target.value }))
                        }
                        onKeyDown={(e) => {
                          if (e.key === "Enter") void handleSave(key);
                        }}
                        className="min-w-0 flex-1 border-b border-jarvis-cyan/30 bg-transparent px-1 py-1 text-sm text-jarvis-text outline-none focus:border-jarvis-cyan"
                      />
                      <button
                        type="button"
                        disabled={busy === key || !(drafts[key] ?? "").trim()}
                        onClick={() => void handleSave(key)}
                        className="glass glass-hover shrink-0 px-3 text-xs uppercase tracking-widest text-jarvis-cyan disabled:opacity-40"
                      >
                        {busy === key ? "…" : "Save"}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>

            {complete && (
              <button
                type="button"
                onClick={handleLaunch}
                className="glass glass-hover mt-6 w-full py-3 text-sm font-bold uppercase tracking-[0.3em] text-glow-cyan"
              >
                Launch Jarvis
              </button>
            )}
          </>
        )}
      </div>
    </WindowFrame>
  );
}

export default SetupWizardWindow;
