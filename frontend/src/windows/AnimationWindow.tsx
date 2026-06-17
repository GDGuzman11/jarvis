/**
 * Window 1 — AnimationWindow. Full-bleed Three.js orb that reacts to the live
 * voice state and audio amplitude from the store. The window itself is
 * frameless/transparent in Tauri, so the orb floats on the desktop.
 */

import type { MouseEvent } from "react";
import { Canvas } from "@react-three/fiber";
import { useStore } from "../lib/store";
import { useBootSound } from "../lib/useBootSound";
import HelixOrb from "../components/HelixOrb";

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
  idle: "",
  listening: "LISTENING",
  thinking: "PROCESSING",
  speaking: "SPEAKING",
};

async function requestShutdown() {
  // Tell the backend to shut down gracefully (fire and forget).
  fetch("http://127.0.0.1:8000/api/shutdown", { method: "POST" }).catch(() => {});

  // Exit the entire Tauri process — kills all 5 windows instantly.
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("exit_app");
  } catch {
    window.close();
  }
}

export function AnimationWindow() {
  useBootSound();
  const voiceState = useStore((s) => s.voiceState);
  const audioLevel = useStore((s) => s.audioLevel);
  const live = voiceState === "listening" || voiceState === "speaking";

  return (
    <div className="relative h-screen w-screen bg-transparent">
      <Canvas
        camera={{ position: [0, 0, 4], fov: 50 }}
        dpr={[1, 2]}
        gl={{ alpha: true, premultipliedAlpha: false, antialias: true }}
        onCreated={({ gl, scene }) => {
          // Keep the Tauri window truly transparent — no opaque backing square.
          gl.setClearColor(0x000000, 0);
          gl.setClearAlpha(0);
          scene.background = null;
        }}
      >
        <HelixOrb voiceState={voiceState} audioLevel={audioLevel} />
      </Canvas>
      {/* Shutdown button — top-right corner, above the Canvas so it stays clickable. */}
      <button
        type="button"
        title="Shutdown Helix"
        onClick={requestShutdown}
        className="absolute right-3 top-3 z-20 flex h-8 w-8 items-center justify-center border border-helix-alert/50 text-helix-alert text-base transition-all duration-200 hover:border-helix-alert hover:text-helix-alert hover:shadow-[0_0_12px_rgba(255,90,90,0.6)]"
      >
        ⏻
      </button>
      <div className="pointer-events-none absolute inset-x-0 bottom-6 flex justify-center">
        <span
          className={`text-xs font-semibold uppercase tracking-[0.5em] ${
            live ? "text-helix-accent text-glow-accent" : "text-helix-gold text-glow-gold"
          }`}
        >
          {STATE_LABEL[voiceState] ?? voiceState}
        </span>
      </div>
      {/* Drag grip strip — pinned to the bottom edge, above the Three.js canvas. */}
      <div
        onMouseDown={startDrag}
        title="Drag to move"
        className="absolute inset-x-0 bottom-0 z-10 flex h-6 cursor-grab items-center justify-center active:cursor-grabbing"
      >
        <span className="pointer-events-none h-1 w-10 rounded-full bg-helix-gold/40" />
      </div>
    </div>
  );
}

export default AnimationWindow;
