/**
 * BrainLayout — a tiny hand-rolled 3D force simulation for the memory brain.
 * No external layout dependency: it reads as a living brain via four forces
 * stepped each frame over typed arrays (cheap for a few hundred nodes):
 *
 *   1. mutual repulsion   — nodes push apart (O(n²); fine ≤ ~400 nodes)
 *   2. edge attraction    — similar memories spring together; rest length
 *                            shrinks as similarity rises, so clusters tighten
 *   3. core tether        — a soft spring toward a target shell radius keeps
 *                            the cloud cohesive and orbiting the nucleus
 *   4. drift              — gentle per-node wander so it never freezes
 *
 * Positions live in `positions` (Float32Array, x,y,z per node) so the renderer
 * can hand them straight to instance matrices / line buffers.
 */

export interface LayoutEdge {
  a: number; // index into positions
  b: number;
  similarity: number; // 0.5..1
}

const REPULSION = 0.012;
const ATTRACTION = 1.4;
const CORE_PULL = 0.9;
const SHELL_RADIUS = 2.6; // target cloud radius around the core
const DAMPING = 0.86;
const MAX_SPEED = 2.2;
const MIN_DIST = 0.18; // clamp so repulsion can't explode at coincident points

export class BrainLayout {
  readonly count: number;
  readonly positions: Float32Array;
  private readonly vel: Float32Array;
  private readonly phase: Float32Array;
  private edges: LayoutEdge[];

  constructor(count: number, edges: LayoutEdge[]) {
    this.count = count;
    this.positions = new Float32Array(count * 3);
    this.vel = new Float32Array(count * 3);
    this.phase = new Float32Array(count);
    this.edges = edges;
    for (let i = 0; i < count; i++) {
      // Seed on a jittered sphere shell so the sim starts cohesive.
      const u = Math.random() * 2 - 1;
      const theta = Math.random() * Math.PI * 2;
      const r = SHELL_RADIUS * (0.5 + Math.random() * 0.6);
      const s = Math.sqrt(1 - u * u);
      this.positions[i * 3] = r * s * Math.cos(theta);
      this.positions[i * 3 + 1] = r * u;
      this.positions[i * 3 + 2] = r * s * Math.sin(theta);
      this.phase[i] = Math.random() * Math.PI * 2;
    }
  }

  /** Append a freshly-grown neuron near the core; grows the typed arrays. */
  static withAppended(prev: BrainLayout, edges: LayoutEdge[]): BrainLayout {
    const next = new BrainLayout(prev.count + 1, edges);
    next.positions.set(prev.positions.subarray(0, prev.count * 3));
    next.vel.set(prev.vel.subarray(0, prev.count * 3));
    next.phase.set(prev.phase.subarray(0, prev.count));
    return next;
  }

  setEdges(edges: LayoutEdge[]): void {
    this.edges = edges;
  }

  /** Advance the simulation by `dt` seconds (clamped for stability). */
  step(dt: number, time: number): void {
    const h = Math.min(dt, 0.05);
    const p = this.positions;
    const v = this.vel;
    const n = this.count;

    // 1. Repulsion (symmetric, single pass).
    for (let i = 0; i < n; i++) {
      const ix = i * 3;
      for (let j = i + 1; j < n; j++) {
        const jx = j * 3;
        let dx = p[ix] - p[jx];
        let dy = p[ix + 1] - p[jx + 1];
        let dz = p[ix + 2] - p[jx + 2];
        let d2 = dx * dx + dy * dy + dz * dz;
        if (d2 < MIN_DIST * MIN_DIST) d2 = MIN_DIST * MIN_DIST;
        const f = (REPULSION / d2) * h;
        const d = Math.sqrt(d2);
        dx /= d; dy /= d; dz /= d;
        v[ix] += dx * f; v[ix + 1] += dy * f; v[ix + 2] += dz * f;
        v[jx] -= dx * f; v[jx + 1] -= dy * f; v[jx + 2] -= dz * f;
      }
    }

    // 2. Edge attraction — rest length shrinks with similarity.
    for (const e of this.edges) {
      const ax = e.a * 3;
      const bx = e.b * 3;
      const dx = p[bx] - p[ax];
      const dy = p[bx + 1] - p[ax + 1];
      const dz = p[bx + 2] - p[ax + 2];
      const d = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1e-3;
      const rest = 1.3 - e.similarity; // sim 0.5→0.8, sim 1→0.3
      const f = ((d - rest) * ATTRACTION * e.similarity * h) / d;
      v[ax] += dx * f; v[ax + 1] += dy * f; v[ax + 2] += dz * f;
      v[bx] -= dx * f; v[bx + 1] -= dy * f; v[bx + 2] -= dz * f;
    }

    // 3. Core tether + 4. drift, then integrate.
    for (let i = 0; i < n; i++) {
      const ix = i * 3;
      const dist = Math.hypot(p[ix], p[ix + 1], p[ix + 2]) || 1e-3;
      const pull = ((SHELL_RADIUS - dist) * CORE_PULL * h) / dist;
      v[ix] += p[ix] * pull;
      v[ix + 1] += p[ix + 1] * pull;
      v[ix + 2] += p[ix + 2] * pull;

      const drift = 0.04 * h;
      v[ix] += Math.sin(time * 0.5 + this.phase[i]) * drift;
      v[ix + 1] += Math.cos(time * 0.4 + this.phase[i]) * drift;

      for (let k = 0; k < 3; k++) {
        v[ix + k] *= DAMPING;
        if (v[ix + k] > MAX_SPEED) v[ix + k] = MAX_SPEED;
        else if (v[ix + k] < -MAX_SPEED) v[ix + k] = -MAX_SPEED;
        p[ix + k] += v[ix + k] * h;
      }
    }
  }
}
