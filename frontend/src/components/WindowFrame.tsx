/**
 * WindowFrame — shared chrome for every HUD window. Provides the dark grid
 * backdrop, a titled header with a live connection indicator, and the staggered
 * boot fade-in (Framer Motion). The `index` prop offsets each window's fade so
 * they cascade ~200ms apart when all 5 open at once.
 */

import type { ReactNode } from "react";
import { motion } from "framer-motion";
import { useStore } from "../lib/store";
import type { ConnectionStatus } from "../lib/types";

const CONN_LABEL: Record<ConnectionStatus, { text: string; color: string }> = {
  connecting: { text: "LINKING", color: "text-jarvis-gold" },
  open: { text: "ONLINE", color: "text-jarvis-cyan" },
  closed: { text: "OFFLINE", color: "text-jarvis-red" },
};

interface WindowFrameProps {
  title: string;
  /** 0-based window index used to stagger the boot fade-in. */
  index?: number;
  children: ReactNode;
}

export function WindowFrame({ title, index = 0, children }: WindowFrameProps) {
  const connection = useStore((s) => s.connection);
  const conn = CONN_LABEL[connection];

  return (
    <motion.div
      className="hud-bg flex h-screen w-screen flex-col overflow-hidden"
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.5, delay: index * 0.2, ease: "easeOut" }}
    >
      <header
        data-tauri-drag-region
        className="flex cursor-grab items-center justify-between border-b border-jarvis-cyan/15 px-5 py-3 active:cursor-grabbing"
      >
        <div className="flex items-center gap-3">
          <span className="h-3 w-3 rotate-45 border border-jarvis-cyan" style={{ boxShadow: "0 0 10px rgba(0,212,255,0.6)" }} />
          <h1 className="text-sm font-bold uppercase tracking-[0.3em] text-glow-cyan">{title}</h1>
        </div>
        <div className="flex items-center gap-2">
          <span className={`h-1.5 w-1.5 rounded-full ${conn.color}`} style={{ background: "currentColor", boxShadow: "0 0 8px currentColor" }} />
          <span className={`text-[10px] font-semibold tracking-widest ${conn.color}`}>{conn.text}</span>
        </div>
      </header>
      <div className="min-h-0 flex-1">{children}</div>
    </motion.div>
  );
}

export default WindowFrame;
