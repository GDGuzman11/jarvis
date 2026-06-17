/**
 * Window 6 — MemoryWindow. An immersive 3D "memory brain": neurons (memory
 * facts + people) float around a glowing core, tethered to it, with brighter
 * lines between semantically related memories. Orbit/zoom to explore, hover a
 * neuron for its contents, and it grows one neuron per new memory (live via
 * the `memory_update` WebSocket event). OPAQUE window → bloom is safe here.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Color } from "three";
import WindowFrame from "../components/WindowFrame";
import MemoryBrain from "../components/memory/MemoryBrain";
import MemoryHoverPanel from "../components/memory/MemoryHoverPanel";
import { fetchMemoryGraph } from "../lib/api";
import { useStore } from "../lib/store";
import { DOMAIN_HEX, DOMAIN_LABELS, DOMAIN_ORDER } from "../lib/memoryStyle";
import type { MemoryNode } from "../lib/types";

/** Collapsible category → color key. Unobtrusive glass card, doesn't block orbit. */
function CategoryLegend() {
  const [open, setOpen] = useState(false);
  return (
    <div className="pointer-events-auto absolute bottom-3 right-3 z-20">
      <div className="glass min-w-[120px] px-2 py-1.5">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-center gap-1 text-[10px] uppercase tracking-widest text-helix-gold focus:outline-none"
        >
          <span>{open ? "▾" : "▸"}</span>
          <span>Categories</span>
        </button>
        {open && (
          <ul className="mt-1.5 space-y-1">
            {DOMAIN_ORDER.map((d) => (
              <li key={d} className="flex items-center gap-2">
                <span
                  className="inline-block h-2.5 w-2.5 shrink-0"
                  style={{ background: DOMAIN_HEX[d], boxShadow: `0 0 5px ${DOMAIN_HEX[d]}` }}
                />
                <span className="text-[10px] tracking-wide text-helix-ink/80">
                  {DOMAIN_LABELS[d] ?? d}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/** Lowercased searchable text for a node. */
function nodeText(n: MemoryNode): string {
  const m = n as Record<string, unknown>;
  return [m.text_full, m.text_preview, m.name, m.role, m.email, m.notes, m.subject, m.category]
    .filter((v) => typeof v === "string")
    .join(" ")
    .toLowerCase();
}

export function MemoryWindow() {
  const nodes = useStore((s) => s.memoryNodes);
  const edges = useStore((s) => s.memoryEdges);
  const setMemoryGraph = useStore((s) => s.setMemoryGraph);

  const [query, setQuery] = useState("");
  const [hovered, setHovered] = useState<MemoryNode | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const panelRef = useRef<HTMLDivElement | null>(null);

  // Pull a fresh brain snapshot. Runs on open and from the ↻ button; live
  // `memory_update` events still patch the graph in between refreshes.
  const loadGraph = useCallback(async () => {
    setRefreshing(true);
    const g = await fetchMemoryGraph();
    if (g) setMemoryGraph(g.nodes, g.edges);
    setRefreshing(false);
  }, [setMemoryGraph]);

  useEffect(() => {
    void loadGraph();
  }, [loadGraph]);

  const visibleIds = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return null;
    const set = new Set<string>();
    for (const n of nodes) if (nodeText(n).includes(q)) set.add(n.id);
    return set;
  }, [query, nodes]);

  return (
    <WindowFrame title="Memory">
      <div className="relative h-full w-full" style={{ background: "#08080a" }}>
        <Canvas
          camera={{ position: [0, 0, 8], fov: 55 }}
          dpr={[1, 2]}
          onCreated={({ scene }) => {
            scene.background = new Color("#08080a");
          }}
        >
          <MemoryBrain
            nodes={nodes}
            edges={edges}
            visibleIds={visibleIds}
            panelRef={panelRef}
            onHover={setHovered}
          />
        </Canvas>

        {/* Search overlay */}
        <div className="pointer-events-auto absolute left-3 top-3 z-20 flex items-center gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="SEARCH MEMORY"
            className="glass w-44 bg-transparent px-2.5 py-1 text-[11px] uppercase tracking-widest text-helix-gold placeholder:text-helix-muted/60 focus:outline-none"
          />
          <span className="text-[10px] uppercase tracking-wider text-helix-muted">
            {nodes.length} {nodes.length === 1 ? "memory" : "memories"}
          </span>
          <button
            type="button"
            onClick={() => void loadGraph()}
            disabled={refreshing}
            title="Refresh memory graph"
            className="hud-btn disabled:opacity-40"
          >
            {refreshing ? "…" : "↻ Refresh"}
          </button>
        </div>

        {/* Category color key */}
        <CategoryLegend />

        {/* Empty / sparse state */}
        {nodes.length === 0 && (
          <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center">
            <p className="text-xs uppercase tracking-[0.4em] text-helix-muted text-glow-gold">
              Helix's memory is still forming…
            </p>
          </div>
        )}

        {/* Hover HUD panel — positioned imperatively by Neurons each frame. */}
        <div
          ref={panelRef}
          className="pointer-events-none absolute left-0 top-0 z-30"
          style={{ opacity: 0, transition: "opacity 120ms ease" }}
        >
          {hovered && <MemoryHoverPanel node={hovered} />}
        </div>
      </div>
    </WindowFrame>
  );
}

export default MemoryWindow;
