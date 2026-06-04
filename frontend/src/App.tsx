/**
 * App — routes the running Tauri window to its component by window label.
 *
 * Each of the 5 windows is launched by Tauri with a fixed label
 * (animation, reasoning, communications, agents, tools). We read the current
 * window's label and render the matching component. When running in a plain
 * browser (e.g. `pnpm dev` without Tauri, or vitest), there is no Tauri window
 * label, so we fall back to the `?window=` query param, then to a dev dashboard
 * that shows every window at once.
 */

import {
  lazy,
  Suspense,
  useEffect,
  useMemo,
  useState,
  type ComponentType,
} from "react";
import { connectWebSocket } from "./lib/websocket";

// Lazy-load each window so the heavy Three.js bundle only ships to the
// Animation window's renderer, not every window.
const AnimationWindow = lazy(() => import("./windows/AnimationWindow"));
const ReasoningWindow = lazy(() => import("./windows/ReasoningWindow"));
const CommunicationsWindow = lazy(() => import("./windows/CommunicationsWindow"));
const AgentsWindow = lazy(() => import("./windows/AgentsWindow"));
const ToolsWindow = lazy(() => import("./windows/ToolsWindow"));
const SetupWizardWindow = lazy(() => import("./windows/SetupWizardWindow"));

export type WindowLabel =
  | "animation"
  | "reasoning"
  | "communications"
  | "agents"
  | "tools"
  | "setup";

const WINDOWS: Record<WindowLabel, ComponentType> = {
  animation: AnimationWindow,
  reasoning: ReasoningWindow,
  communications: CommunicationsWindow,
  agents: AgentsWindow,
  tools: ToolsWindow,
  setup: SetupWizardWindow,
};

/** Resolve the active window label from Tauri, then URL query, else null. */
function resolveLabel(): WindowLabel | null {
  // Tauri injects __TAURI_INTERNALS__ with the current window metadata.
  const internals = (globalThis as unknown as {
    __TAURI_INTERNALS__?: { metadata?: { currentWindow?: { label?: string } } };
  }).__TAURI_INTERNALS__;
  const tauriLabel = internals?.metadata?.currentWindow?.label;
  const queryLabel = new URLSearchParams(window.location.search).get("window");
  const label = (tauriLabel || queryLabel || "").toLowerCase();
  return label in WINDOWS ? (label as WindowLabel) : null;
}

function App() {
  const label = useMemo(resolveLabel, []);
  const [active, setActive] = useState<WindowLabel | null>(label);

  useEffect(() => {
    // One WebSocket connection per renderer process / window.
    connectWebSocket();
  }, []);

  if (active) {
    const Window = WINDOWS[active];
    return (
      <Suspense fallback={<div className="hud-bg h-screen w-screen" />}>
        {!label && (
          <button
            type="button"
            onClick={() => setActive(null)}
            className="glass glass-hover fixed top-3 left-3 z-50 px-3 py-1 text-xs uppercase tracking-widest text-jarvis-cyan"
          >
            ← Back
          </button>
        )}
        <Window />
      </Suspense>
    );
  }

  // Dev dashboard — no Tauri label and no ?window= param. Lets a single browser
  // tab preview each window for development without the native multi-window shell.
  return (
    <div className="hud-bg min-h-screen p-6">
      <h1 className="mb-4 text-lg font-bold uppercase tracking-[0.4em] text-glow-cyan">
        Jarvis HUD — Dev Preview
      </h1>
      <div className="flex flex-wrap gap-2">
        {(Object.keys(WINDOWS) as WindowLabel[]).map((w) => (
          <button
            key={w}
            type="button"
            onClick={() => setActive(w)}
            className="glass glass-hover px-4 py-2 text-sm uppercase tracking-widest text-jarvis-cyan"
          >
            {w}
          </button>
        ))}
      </div>
      <p className="mt-4 text-xs text-jarvis-muted">
        Select a window to preview. In the packaged app each opens in its own
        Tauri window automatically.
      </p>
    </div>
  );
}

export default App;
