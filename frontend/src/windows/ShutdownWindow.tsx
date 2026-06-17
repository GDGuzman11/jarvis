/**
 * ShutdownWindow — a tiny standalone window holding just the ⏻ power button,
 * split out of AnimationWindow so the shutdown control floats independently of
 * the orb.
 *
 * Interaction: a quick **click** on the button shuts the backend down and exits
 * the whole Tauri process; **click-and-hold then drag** moves the window. The
 * two are disambiguated by a small movement threshold so holding the button to
 * reposition never triggers an accidental shutdown.
 */

import { useRef, type MouseEvent } from "react";

async function startDragging() {
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

const DRAG_THRESHOLD_PX = 4;

export function ShutdownWindow() {
  const downAt = useRef<{ x: number; y: number } | null>(null);
  const dragged = useRef(false);

  function onMouseDown(e: MouseEvent) {
    if (e.button !== 0) return;
    downAt.current = { x: e.clientX, y: e.clientY };
    dragged.current = false;
  }

  function onMouseMove(e: MouseEvent) {
    if (!downAt.current || dragged.current) return;
    const dx = e.clientX - downAt.current.x;
    const dy = e.clientY - downAt.current.y;
    if (Math.hypot(dx, dy) > DRAG_THRESHOLD_PX) {
      // Past the threshold → treat as a drag, hand off to the OS window move.
      dragged.current = true;
      void startDragging();
    }
  }

  function onMouseUp() {
    downAt.current = null;
  }

  function onClick() {
    // A click that followed a drag must not shut Helix down.
    if (dragged.current) {
      dragged.current = false;
      return;
    }
    void requestShutdown();
  }

  return (
    <div
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      className="flex h-screen w-screen cursor-grab items-center justify-center bg-transparent active:cursor-grabbing"
    >
      <button
        type="button"
        title="Click to shut down · hold and drag to move"
        onClick={onClick}
        className="flex h-9 w-9 items-center justify-center border border-helix-alert/50 text-helix-alert text-lg transition-all duration-200 hover:border-helix-alert hover:text-helix-alert hover:shadow-[0_0_12px_rgba(255,90,90,0.6)]"
      >
        ⏻
      </button>
    </div>
  );
}

export default ShutdownWindow;
