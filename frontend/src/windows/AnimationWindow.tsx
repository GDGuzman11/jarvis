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
  idle: "JARVIS",
  listening: "LISTENING",
  thinking: "PROCESSING",
  speaking: "SPEAKING",
};

async function requestShutdown() {
  // Tell the backend to broadcast shutdown to all other windows — fire and forget.
  fetch("http://127.0.0.1:8000/api/shutdown", { method: "POST" }).catch(() => {});

  // Directly close this window without waiting for the WebSocket round-trip.
  await new Promise((r) => setTimeout(r, 150));
  try {
    const { getCurrentWebviewWindow } = await import("@tauri-apps/api/webviewWindow");
    await getCurrentWebviewWindow().close();
  } catch {
    window.close();
  }
}

export function AnimationWindow() {
  useBootSound();
  const voiceState = useStore((s) => s.voiceState);
  const audioLevel = useStore((s) => s.audioLevel);

  return (
    <div className="relative h-screen w-screen bg-jarvis-bg">
      <Canvas camera={{ position: [0, 0, 4], fov: 50 }} dpr={[1, 2]}>
        <JarvisOrb voiceState={voiceState} audioLevel={audioLevel} />
      </Canvas>
      {/* Connection beams — radiating from orb centre to the other windows. */}
      <svg
        className="pointer-events-none absolute inset-0 z-10 h-full w-full"
        viewBox="0 0 360 360"
        preserveAspectRatio="none"
      >
        {/* Reasoning (left) */}
        <path id="beam-reasoning" d="M180,180 L0,180" stroke="#00d4ff" strokeWidth="0.5" strokeOpacity="0.12" fill="none" />
        <circle r="2" fill="#00ffff" opacity="0.8">
          <animateMotion dur="2.2s" repeatCount="indefinite" path="M180,180 L0,180" />
        </circle>

        {/* Communications (upper-right) */}
        <path id="beam-comms" d="M180,180 L360,72" stroke="#00d4ff" strokeWidth="0.5" strokeOpacity="0.12" fill="none" />
        <circle r="2" fill="#00ffff" opacity="0.8">
          <animateMotion dur="1.8s" repeatCount="indefinite" path="M180,180 L360,72" />
        </circle>

        {/* Agents (bottom) */}
        <path id="beam-agents" d="M180,180 L180,360" stroke="#00d4ff" strokeWidth="0.5" strokeOpacity="0.12" fill="none" />
        <circle r="2" fill="#00ffff" opacity="0.8">
          <animateMotion dur="2.5s" repeatCount="indefinite" path="M180,180 L180,360" />
        </circle>

        {/* Tools (lower-right) */}
        <path id="beam-tools" d="M180,180 L360,270" stroke="#00d4ff" strokeWidth="0.5" strokeOpacity="0.12" fill="none" />
        <circle r="2" fill="#00ffff" opacity="0.8">
          <animateMotion dur="2.0s" repeatCount="indefinite" path="M180,180 L360,270" />
        </circle>

        {/* Centre node */}
        <circle cx="180" cy="180" r="4" fill="none" stroke="#00d4ff" strokeWidth="0.5" strokeOpacity="0.4" />
      </svg>
      {/* Shutdown button — top-right corner, above the Canvas so it stays clickable. */}
      <button
        type="button"
        title="Shutdown Jarvis"
        onClick={requestShutdown}
        className="absolute right-3 top-3 z-20 flex h-8 w-8 items-center justify-center border border-red-500/50 text-red-400 text-base transition-all duration-200 hover:border-red-400 hover:text-red-300 hover:shadow-[0_0_12px_rgba(255,59,92,0.6)]"
      >
        ⏻
      </button>
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
