/**
 * Type → visual-style lookup for the memory brain. Pure data (no Three.js / no
 * React) so it can be unit-tested and reused. Adding a future `project` node
 * type means adding one branch here — nothing else in the renderer changes.
 *
 * Palette (gold / white / aqua / red — NO cyan):
 *   memory          → gold   #ffc247  (brighter ∝ importance, bigger ∝ recall)
 *   memory conflict → red    #FF5A5A
 *   person          → silver-white #d6dce8
 *   generic/future  → muted neutral
 * Recently-recalled memories carry an aqua #3fe3d0 accent flag the renderer
 * uses to add a cool glow.
 */

import type { MemoryNode } from "./types";

export type Rgb = [number, number, number];

const GOLD: Rgb = [1.0, 0.7608, 0.2784]; // #ffc247
const RED: Rgb = [1.0, 0.353, 0.353]; // #FF5A5A
const SILVER: Rgb = [0.839, 0.863, 0.91]; // #d6dce8
const MUTED: Rgb = [0.604, 0.58, 0.533]; // #9a9488
export const AQUA: Rgb = [0.247, 0.89, 0.816]; // #3fe3d0

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
      color: conflict ? RED : GOLD,
      size: 0.05 + Math.log(access + 1) * 0.014,
      glow: 0.45 + importance * 0.55,
      recalled,
    };
  }
  if (node.type === "person") {
    return { color: SILVER, size: 0.08, glow: 0.7, recalled: false };
  }
  return { color: MUTED, size: 0.055, glow: 0.4, recalled: false };
}

/** Short human label for the type badge in the hover panel. */
export function typeBadge(node: MemoryNode): { label: string; rgb: Rgb } {
  if (node.type === "memory") {
    if (node.conflicting_fact_ids != null && node.conflicting_fact_ids !== "")
      return { label: "CONTRADICTION", rgb: RED };
    return { label: "MEMORY", rgb: GOLD };
  }
  if (node.type === "person") return { label: "PERSON", rgb: SILVER };
  return { label: String(node.type ?? "NODE").toUpperCase(), rgb: MUTED };
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
