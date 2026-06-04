/**
 * Window 1 — AnimationWindow. Full-bleed Three.js orb that reacts to the live
 * voice state and audio amplitude from the store. The window itself is
 * frameless/transparent in Tauri, so the orb floats on the desktop.
 */

import type { MouseEvent } from "react";
import { Canvas } from "@react-three/fiber";
import { useStore } from "../lib/store";
import { useBootSound } from "../lib/useBootSound";
import JarvisOrb from "../components/JarvisOrb";

async function startDrag(e: MouseEvent) {
  if (e.button !== 0) return;
  try {
    const { getCurrentWebviewWindow } = await import("@tauri-apps/api/webviewWindow");
    await getCurrentWebviewWindow().startDragging();
  } catch {
    // Browser mode — dragging not available.
  }
}

const STATE_LABEL: Record<string, string> = {
  idle: "STANDBY",
  listening: "LISTENING",
  thinking: "PROCESSING",
  speaking: "SPEAKING",
};

async function requestShutdown() {
  try {
    await fetch("http://127.0.0.1:8000/api/shutdown", { method: "POST" });
  } catch {
    // Backend already down — the WS disconnect will close the windows.
  }
}

export function AnimationWindow() {
  useBootSound();
  const voiceState = useStore((s) => s.voiceState);
  const audioLevel = useStore((s) => s.audioLevel);

  return (
    <div className="relative h-screen w-screen bg-jarvis-bg">
      {/* Shutdown button — top-right corner */}
      <button
        type="button"
        title="Shutdown Jarvis"
        onClick={requestShutdown}
        className="absolute right-3 top-3 z-10 flex h-7 w-7 items-center justify-center border border-red-500/30 text-sm text-red-500/50 transition-colors hover:border-red-500 hover:text-red-500"
      >
        ⏻
      </button>
      <Canvas camera={{ position: [0, 0, 4], fov: 50 }} dpr={[1, 2]}>
        <JarvisOrb voiceState={voiceState} audioLevel={audioLevel} />
      </Canvas>
      <div className="pointer-events-none absolute inset-x-0 bottom-6 flex justify-center">
        <span className="text-xs font-semibold uppercase tracking-[0.5em] text-glow-cyan">
          {STATE_LABEL[voiceState] ?? voiceState}
        </span>
      </div>
      {/* Drag grip strip — pinned to the bottom edge, above the Three.js canvas. */}
      <div
        onMouseDown={startDrag}
        title="Drag to move"
        className="absolute inset-x-0 bottom-0 z-10 flex h-6 cursor-grab items-center justify-center active:cursor-grabbing"
      >
        <span className="pointer-events-none h-1 w-10 rounded-full bg-jarvis-cyan/40" />
      </div>
    </div>
  );
}

export default AnimationWindow;
