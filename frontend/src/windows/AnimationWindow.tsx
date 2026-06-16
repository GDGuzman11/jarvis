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
  idle: "HELIX",
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
      <Canvas camera={{ position: [0, 0, 4], fov: 50 }} dpr={[1, 2]}>
        <HelixOrb voiceState={voiceState} audioLevel={audioLevel} />
      </Canvas>
      {/* Connection beams — radiating from orb centre to the other windows. */}
      <svg
        className="pointer-events-none absolute inset-0 z-10 h-full w-full"
        viewBox="0 0 360 360"
        preserveAspectRatio="none"
      >
        {/* Reasoning (left) */}
        <path id="beam-reasoning" d="M180,180 L0,180" stroke="#ffc247" strokeWidth="0.5" strokeOpacity="0.12" fill="none" />
        <circle r="2" fill="#3fe3d0" opacity="0.8">
          <animateMotion dur="2.2s" repeatCount="indefinite" path="M180,180 L0,180" />
        </circle>

        {/* Communications (upper-right) */}
        <path id="beam-comms" d="M180,180 L360,72" stroke="#ffc247" strokeWidth="0.5" strokeOpacity="0.12" fill="none" />
        <circle r="2" fill="#3fe3d0" opacity="0.8">
          <animateMotion dur="1.8s" repeatCount="indefinite" path="M180,180 L360,72" />
        </circle>

        {/* Agents (bottom) */}
        <path id="beam-agents" d="M180,180 L180,360" stroke="#ffc247" strokeWidth="0.5" strokeOpacity="0.12" fill="none" />
        <circle r="2" fill="#3fe3d0" opacity="0.8">
          <animateMotion dur="2.5s" repeatCount="indefinite" path="M180,180 L180,360" />
        </circle>

        {/* Tools (lower-right) */}
        <path id="beam-tools" d="M180,180 L360,270" stroke="#ffc247" strokeWidth="0.5" strokeOpacity="0.12" fill="none" />
        <circle r="2" fill="#3fe3d0" opacity="0.8">
          <animateMotion dur="2.0s" repeatCount="indefinite" path="M180,180 L360,270" />
        </circle>

        {/* Centre node */}
        <circle cx="180" cy="180" r="4" fill="none" stroke="#ffc247" strokeWidth="0.5" strokeOpacity="0.4" />
      </svg>
      {/* Shutdown button — top-right corner, above the Canvas so it stays clickable. */}
      <button
        type="button"
        title="Shutdown Helix"
        onClick={requestShutdown}
        className="absolute right-3 top-3 z-20 flex h-8 w-8 items-center justify-center border border-jarvis-red/50 text-jarvis-red text-base transition-all duration-200 hover:border-jarvis-red hover:text-jarvis-red hover:shadow-[0_0_12px_rgba(224,144,46,0.6)]"
      >
        ⏻
      </button>
      {/* Top tagline + identity flourishes (reference hub motif). */}
      <div className="pointer-events-none absolute inset-x-0 top-3 flex flex-col items-center gap-0.5">
        <span className="text-[9px] font-semibold uppercase tracking-[0.55em] text-jarvis-cyan/70 text-glow-gold">
          THINK · PLAN · ACT · ELEVATE
        </span>
        <span className="text-[7px] uppercase tracking-[0.4em] text-jarvis-muted">
          HELIX · CORE INTELLIGENCE
        </span>
      </div>
      <div className="pointer-events-none absolute inset-x-0 bottom-6 flex justify-center">
        <span
          className={`text-xs font-semibold uppercase tracking-[0.5em] ${
            live ? "text-jarvis-accent text-glow-accent" : "text-jarvis-cyan text-glow-gold"
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
        <span className="pointer-events-none h-1 w-10 rounded-full bg-jarvis-cyan/40" />
      </div>
    </div>
  );
}

export default AnimationWindow;
