/**
 * StreamViewer — live token stream display. Auto-scrolls to the bottom as new
 * tokens arrive and shows a blinking cursor while the model is producing
 * output. Pure presentation; text comes from the store.
 */

import { useEffect, useRef } from "react";

interface StreamViewerProps {
  text: string;
  /** When true, render a blinking cursor to signal active streaming. */
  active: boolean;
}

export function StreamViewer({ text, active }: StreamViewerProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [text]);

  return (
    <div className="hud-scroll h-full overflow-y-auto p-4 font-mono text-sm leading-relaxed text-helix-ink/90">
      {text.length === 0 ? (
        <span className="italic text-helix-muted">Awaiting model output…</span>
      ) : (
        <span className="whitespace-pre-wrap break-words">{text}</span>
      )}
      {active && (
        <span className="ml-0.5 inline-block h-4 w-2 translate-y-0.5 bg-helix-gold animate-pulse-glow" />
      )}
      <div ref={endRef} />
    </div>
  );
}

export default StreamViewer;
