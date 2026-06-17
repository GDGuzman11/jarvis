/**
 * Type → visual-style lookup for the memory brain. Pure data (no Three.js / no
 * React) so it can be unit-tested and reused. Adding a future `project` node
 * type means adding one branch here — nothing else in the renderer changes.
 *
 * A memory node's BASE hue comes from its `domain` (the locked 10-category
 * palette below — NO cyan): personal gold, atlas bone, ben blue, kado green,
 * sentinel red, vega pink, quill orange, project teal, people purple, general
 * gray. brighter ∝ importance, bigger ∝ recall. Layered STATES sit on top of
 * that base hue: contradiction → red, recently-recalled → aqua #3fe3d0 rim,
 * search-hit → bright/enlarge glow (applied by the renderer, not here).
 */

import type { MemoryNode } from "./types";

export type Rgb = [number, number, number];

const RED: Rgb = [1.0, 0.353, 0.353]; // #FF5A5A
export const AQUA: Rgb = [0.247, 0.89, 0.816]; // #3fe3d0

/** Parse "#rrggbb" → normalised [r,g,b]. */
function hexToRgb(hex: string): Rgb {
  const h = hex.replace("#", "");
  return [
    parseInt(h.slice(0, 2), 16) / 255,
    parseInt(h.slice(2, 4), 16) / 255,
    parseInt(h.slice(4, 6), 16) / 255,
  ];
}

/* ── Category (domain) palette ─────────────────────────────────────────────
 * A memory node's base hue is driven by its `domain`, one of the locked 10
 * categories. Reused by both the neuron renderer (Rgb) and the React legend /
 * confirm badge (hex), so the two always agree. NO cyan. */
export const DOMAIN_HEX: Record<string, string> = {
  personal: "#ffc247",
  atlas: "#f0ead6",
  ben: "#5ab0ff",
  kado: "#4fd18b",
  sentinel: "#ff5a5a",
  vega: "#ff6fd0",
  quill: "#ff9e42",
  project: "#3fe3d0",
  people: "#b06fff",
  general: "#9a9488",
};

/** Display labels for the legend (and confirm badge fallback). */
export const DOMAIN_LABELS: Record<string, string> = {
  personal: "Personal",
  atlas: "Atlas · Production",
  ben: "Ben · Frontend",
  kado: "Kado · Backend",
  sentinel: "Sentinel · Security",
  vega: "Vega · Marketing",
  quill: "Quill · Content",
  project: "Project",
  people: "People",
  general: "General",
};

/** Legend / iteration order. */
export const DOMAIN_ORDER: string[] = [
  "personal",
  "atlas",
  "ben",
  "kado",
  "sentinel",
  "vega",
  "quill",
  "project",
  "people",
  "general",
];

const DOMAIN_RGB: Record<string, Rgb> = Object.fromEntries(
  Object.entries(DOMAIN_HEX).map(([k, v]) => [k, hexToRgb(v)]),
);

/** Resolve a domain key to its hex (unknown / missing → general gray). */
export function domainColorCss(domain?: string | null): string {
  const d = (domain ?? "").toLowerCase();
  return DOMAIN_HEX[d] ?? DOMAIN_HEX.general;
}

/** Resolve a domain key to its Rgb (unknown / missing → general gray). */
export function domainColorRgb(domain?: string | null): Rgb {
  const d = (domain ?? "").toLowerCase();
  return DOMAIN_RGB[d] ?? DOMAIN_RGB.general;
}

/**
 * A memory node's domain: prefer the new `domain` column, fall back to the
 * legacy `category` value (when it happens to name a domain), else general.
 * The backend already maps legacy facts, so `domain` is normally present —
 * this is purely defensive.
 */
function nodeDomain(node: MemoryNode): string {
  const m = node as Record<string, unknown>;
  const d = typeof m.domain === "string" ? m.domain.toLowerCase() : "";
  if (d && DOMAIN_HEX[d]) return d;
  const c = typeof m.category === "string" ? m.category.toLowerCase() : "";
  if (c && DOMAIN_HEX[c]) return c;
  return "general";
}

/** How recent counts as "recently recalled" (aqua glow). */
const RECENT_MS = 1000 * 60 * 60 * 24 * 3; // 3 days

export interface NodeStyle {
  /** Base RGB before importance brightening. */
  color: Rgb;
  /** Sphere radius in world units. */
  size: number;
  /** 0..1 emphasis driving bloom intensity. */
  glow: number;
  /** True → renderer mixes in an aqua rim (recently recalled). */
  recalled: boolean;
}

function isRecent(iso: string | null | undefined): boolean {
  if (!iso) return false;
  const t = Date.parse(iso);
  return Number.isFinite(t) && Date.now() - t < RECENT_MS;
}

/** Resolve a node's color, size and glow from its type + quality fields. */
export function nodeStyle(node: MemoryNode): NodeStyle {
  if (node.type === "memory") {
    const importance = clamp01(asNum(node.importance, 0.4));
    const access = asNum(node.access_count, 0);
    const conflict = node.conflicting_fact_ids != null && node.conflicting_fact_ids !== "";
    const recalled = isRecent(node.last_recalled_at as string | null);
    return {
      // Base hue = category/domain; a contradiction overrides to red (the
      // layered conflict state). brighter ∝ importance, bigger ∝ recall.
      color: conflict ? RED : domainColorRgb(nodeDomain(node)),
      size: 0.05 + Math.log(access + 1) * 0.014,
      glow: 0.45 + importance * 0.55,
      recalled,
    };
  }
  if (node.type === "person") {
    return { color: domainColorRgb("people"), size: 0.08, glow: 0.7, recalled: false };
  }
  return { color: domainColorRgb("general"), size: 0.055, glow: 0.4, recalled: false };
}

/** Short human label for the type badge in the hover panel. */
export function typeBadge(node: MemoryNode): { label: string; rgb: Rgb } {
  if (node.type === "memory") {
    if (node.conflicting_fact_ids != null && node.conflicting_fact_ids !== "")
      return { label: "CONTRADICTION", rgb: RED };
    const domain = nodeDomain(node);
    return { label: (DOMAIN_LABELS[domain] ?? domain).toUpperCase(), rgb: domainColorRgb(domain) };
  }
  if (node.type === "person") return { label: "PERSON", rgb: domainColorRgb("people") };
  return { label: String(node.type ?? "NODE").toUpperCase(), rgb: domainColorRgb("general") };
}

export function rgbToCss(rgb: Rgb, alpha = 1): string {
  const [r, g, b] = rgb;
  return `rgba(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)}, ${alpha})`;
}

function asNum(v: unknown, fallback: number): number {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : fallback;
}
function clamp01(n: number): number {
  return Math.max(0, Math.min(1, n));
}
