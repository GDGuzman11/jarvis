import type { ReactNode, MouseEvent } from "react";
import { motion } from "framer-motion";
import { useStore } from "../lib/store";
import type { ConnectionStatus } from "../lib/types";

// glow strings MUST retain a literal "0.5" alpha — the badge background is derived
// below via conn.glow.replace('0.5','0.08'). open = live aqua accent; offline = red alert.
const CONN_CONFIG: Record<ConnectionStatus, { label: string; color: string; glow: string }> = {
  connecting: { label: "LINKING", color: "text-helix-gold-bright",   glow: "rgba(255,194,71,0.5)" },
  open:       { label: "ONLINE",  color: "text-helix-accent", glow: "rgba(63,227,208,0.5)" },
  closed:     { label: "OFFLINE", color: "text-helix-alert",    glow: "rgba(255,90,90,0.5)" },
};

async function startDrag(e: MouseEvent) {
  if (e.button !== 0) return;
  try {
    const { getCurrentWebviewWindow } = await import("@tauri-apps/api/webviewWindow");
    await getCurrentWebviewWindow().startDragging();
  } catch { /* browser mode */ }
}

interface WindowFrameProps {
  title: string;
  index?: number;
  children: ReactNode;
}

export function WindowFrame({ title, index = 0, children }: WindowFrameProps) {
  const connection = useStore((s) => s.connection);
  const conn = CONN_CONFIG[connection];

  return (
    <motion.div
      className="hud-bg hud-corners relative flex h-screen w-screen flex-col overflow-hidden"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.15, ease: "easeOut" }}
    >
      {/* Flowing data-stream top border */}
      <div className="data-stream-top absolute inset-x-0 top-0 h-0 w-full" />

      {/* Header */}
      <header
        onMouseDown={startDrag}
        className="relative z-10 flex cursor-grab select-none items-center justify-between border-b border-helix-gold/20 bg-black/20 px-4 py-2.5 active:cursor-grabbing"
      >
        {/* Left: accent + title */}
        <div className="flex items-center gap-2.5">
          <div className="flex gap-1">
            <span className="h-3 w-px bg-helix-gold opacity-80" />
            <span className="h-3 w-px bg-helix-gold/40" />
          </div>
          <span className="text-[11px] font-bold uppercase tracking-[0.35em] text-glow-gold">
            {title}
          </span>
        </div>

        {/* Right: status badge */}
        <div
          className={`flex items-center gap-1.5 border px-2 py-0.5 text-[9px] font-bold tracking-widest ${conn.color}`}
          style={{
            borderColor: conn.glow,
            background: `${conn.glow.replace('0.5', '0.08')}`,
            boxShadow: `0 0 8px ${conn.glow}`,
          }}
        >
          <span
            className="h-1.5 w-1.5 animate-pulse-glow"
            style={{ background: 'currentColor', display: 'block' }}
          />
          {conn.label}
        </div>
      </header>

      {/* Content */}
      <div className="min-h-0 flex-1 overflow-hidden">
        {children}
      </div>

      {/* Bottom corner accents */}
      <div className="pointer-events-none absolute bottom-0 left-0 h-2 w-2 border-b border-l border-helix-gold/40" />
      <div className="pointer-events-none absolute bottom-0 right-0 h-2 w-2 border-b border-r border-helix-gold/40" />
    </motion.div>
  );
}

export default WindowFrame;
