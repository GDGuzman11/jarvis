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
