/**
 * MemoryHoverPanel — the HUD card shown when a neuron is hovered. Pure
 * presentation: the outer positioned wrapper (and its imperative screen
 * placement) lives in MemoryWindow; this just renders the node's contents.
 */

import type { MemoryFactNode, MemoryNode, MemoryPersonNode } from "../../lib/types";
import { rgbToCss, typeBadge } from "../../lib/memoryStyle";

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return "—";
  return new Date(t).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function relative(iso: string | null | undefined): string {
  if (!iso) return "never";
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return "never";
  const days = Math.floor((Date.now() - t) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;
  return `${Math.floor(days / 30)} mo ago`;
}

const ROW = "flex justify-between gap-4 text-[11px]";
const KEY = "text-helix-muted uppercase tracking-wider";

export default function MemoryHoverPanel({ node }: { node: MemoryNode }) {
  const badge = typeBadge(node);
  return (
    <div
      className="glass w-64 px-3.5 py-3"
      style={{ background: "rgba(8,14,28,0.92)", backdropFilter: "blur(24px)" }}
    >
      <span
        className="mb-2 inline-block px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.2em]"
        style={{ color: rgbToCss(badge.rgb), border: `1px solid ${rgbToCss(badge.rgb, 0.5)}` }}
      >
        {badge.label}
      </span>

      {node.type === "person" ? (
        <PersonBody node={node as MemoryPersonNode} />
      ) : node.type === "memory" ? (
        <FactBody node={node as MemoryFactNode} />
      ) : (
        <p className="text-xs text-helix-ink">{String((node as { text_full?: string }).text_full ?? node.id)}</p>
      )}
    </div>
  );
}

function FactBody({ node }: { node: MemoryFactNode }) {
  return (
    <>
      <p className="mb-2.5 text-xs leading-snug text-helix-ink">{node.text_full || node.text_preview}</p>
      <div className="space-y-1 border-t border-helix-gold/15 pt-2">
        <div className={ROW}>
          <span className={KEY}>Importance</span>
          <span className="text-helix-gold">{node.importance?.toFixed(2) ?? "—"}</span>
        </div>
        <div className={ROW}>
          <span className={KEY}>Recalled</span>
          <span className="text-helix-ink">{node.access_count ?? 0} times</span>
        </div>
        <div className={ROW}>
          <span className={KEY}>Confidence</span>
          <span className="text-helix-ink">{node.confidence?.toFixed(2) ?? "—"}</span>
        </div>
        <div className={ROW}>
          <span className={KEY}>Created</span>
          <span className="text-helix-ink">{fmtDate(node.created_at)}</span>
        </div>
        <div className={ROW}>
          <span className={KEY}>Last recall</span>
          <span className={node.last_recalled_at ? "text-helix-accent" : "text-helix-muted"}>
            {relative(node.last_recalled_at)}
          </span>
        </div>
      </div>
    </>
  );
}

function PersonBody({ node }: { node: MemoryPersonNode }) {
  return (
    <>
      <p className="mb-1 text-sm font-semibold text-helix-ink">{node.name}</p>
      {node.role && <p className="mb-2 text-[11px] text-helix-muted">{node.role}</p>}
      <div className="space-y-1 border-t border-helix-gold/15 pt-2">
        {node.email && (
          <div className={ROW}>
            <span className={KEY}>Email</span>
            <span className="truncate text-helix-ink">{node.email}</span>
          </div>
        )}
        {node.notes && <p className="text-[11px] leading-snug text-helix-ink">{node.notes}</p>}
        <div className={ROW}>
          <span className={KEY}>Last contact</span>
          <span className="text-helix-ink">{relative(node.last_contact_at)}</span>
        </div>
      </div>
    </>
  );
}
