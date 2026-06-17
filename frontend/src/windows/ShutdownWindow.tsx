/**
 * ShutdownWindow — a tiny standalone window holding just the ⏻ power button,
 * split out of AnimationWindow so the shutdown control floats independently of
 * the orb. Clicking the button shuts the backend down and exits the whole Tauri
 * process; the surrounding margin is a drag region so the little window can be
 * repositioned.
 */

import type { MouseEvent } from "react";

async function startDrag(e: MouseEvent) {
  if (e.button !== 0) return;
  try {
    const { getCurrentWebviewWindow } = await import("@tauri-apps/api/webviewWindow");
    await getCurrentWebviewWindow().startDragging();
  } catch {
    // Browser mode — dragging not available.
  }
}

async function requestShutdown() {
  // Tell the backend to shut down gracefully (fire and forget).
  fetch("http://127.0.0.1:8000/api/shutdown", { method: "POST" }).catch(() => {});

  // Exit the entire Tauri process — closes every Helix window instantly.
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("exit_app");
  } catch {
    window.close();
  }
}

export function ShutdownWindow() {
  return (
    <div
      onMouseDown={startDrag}
      title="Drag to move"
      className="flex h-screen w-screen cursor-grab items-center justify-center bg-transparent active:cursor-grabbing"
    >
      <button
        type="button"
        title="Shutdown Helix"
        // Don't start a window drag when pressing the button itself.
        onMouseDown={(e) => e.stopPropagation()}
        onClick={requestShutdown}
        className="flex h-9 w-9 items-center justify-center border border-helix-alert/50 text-helix-alert text-lg transition-all duration-200 hover:border-helix-alert hover:text-helix-alert hover:shadow-[0_0_12px_rgba(255,90,90,0.6)]"
      >
        ⏻
      </button>
    </div>
  );
}

export default ShutdownWindow;
