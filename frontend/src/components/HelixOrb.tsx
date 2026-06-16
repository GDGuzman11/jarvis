/**
 * HelixOrb — the Neural Intelligence Orb.
 *
 * A floating holographic sphere built from ~350 interconnected neuron nodes.
 * Thin glowing pathways (LineSegments) form a neural-network graph across the
 * surface; ~20% of those pathways are red "freedom pathways" representing the
 * AI's self-determination. Mathematical/code symbols drift inside the sphere.
 * Three nested glow spheres + a flickering hologram shell give it volume.
 *
 * Activation propagates through the graph as cascades: a random node fires and
 * the energy spreads outward through the adjacency graph up to CASCADE_DEPTH
 * hops, brightening nodes and the connections between them. Firing rate, cascade
 * intensity, colour tint, symbol speed and red-pathway glow all vary by
 * voiceState and lerp smoothly between states inside `useFrame`.
 *
 * The `HelixOrb({ voiceState, audioLevel })` signature, `BASE_RADIUS = 1.2`,
 * golden-spiral node distribution, AdditiveBlending + depthWrite:false on every
 * material, and the speaking-state audioLevel pulse are all preserved from the
 * previous orb. Everything else (the 2500-particle cloud, synaptic bezier arcs,
 * jagged discharge arcs) has been removed.
 */

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import {
  AdditiveBlending,
  CanvasTexture,
  Color,
  Group,
  IcosahedronGeometry,
  Mesh,
  MeshBasicMaterial,
  SphereGeometry,
  Sprite,
  SpriteMaterial,
  Vector3,
  type LineSegments as ThreeLineSegments,
  type Points as ThreePoints,
} from "three";
import type { VoiceState } from "../lib/types";

// --- Core geometry ----------------------------------------------------------
const BASE_RADIUS = 1.2; // preserved sphere size
const NODE_COUNT = 350; // neuron nodes
const NEIGHBOR_K = 4; // nearest neighbours linked per node
const RED_RATIO = 0.2; // 20% of connections are red freedom pathways
const SYMBOL_COUNT = 30; // interior drifting symbols
const CASCADE_DEPTH = 6; // hops an activation cascade spreads

// Symbols rendered inside the sphere — maths + code glyphs.
const SYMBOLS = [
  "∑", "π", "∞", "√", "∂", "∫", "∇", "Δ", "λ", "φ",
  "ψ", "α", "β", "Ω", "≡", "≈", "⊕", "→", "{}", "[]",
  "01", "if", ">>", "0x", "⚡", "∈", "∮", "ℝ", "∀", "∃",
];

// --- Colour palette ---------------------------------------------------------
// Champagne-gold neural mass with a cool aqua accent. The "freedom pathways"
// (formerly red) glow aqua against the gold to read as self-determination.
const COL_NEURON_BASE = new Color("#ffe9c2"); // warm white-gold node
const COL_NEURON_HOT = new Color("#ffffff"); // white-hot active node
const COL_NEURON_GOLD = new Color("#ffc247"); // gold tint (thinking)
const COL_NEURON_CYAN = new Color("#6ff0e2"); // aqua surge (speaking)
const COL_CONN_DIM = new Color("#5a4410"); // dim gold connection
const COL_CONN_HOT = new Color("#ffd66b"); // bright gold connection
const COL_RED_DIM = new Color("#1f6e66"); // dim aqua freedom pathway
const COL_RED_HOT = new Color("#8ffaec"); // vivid aqua freedom pathway

const STATE_GLOW: Record<VoiceState, Color> = {
  idle: new Color("#3a2e10"), // dim gold
  listening: new Color("#1f6e66"), // aqua accent
  thinking: new Color("#aa7700"), // bright gold
  speaking: new Color("#1f8c82"), // aqua accent
};

/** Per-state behaviour knobs the animation lerps toward. */
const STATE_PARAMS: Record<
  VoiceState,
  {
    scale: number;
    brightness: number;
    neuronRate: number; // cascades per second
    symbolSpeed: number;
    redGlow: number;
  }
> = {
  idle: { scale: 1.0, brightness: 0.7, neuronRate: 0.4, symbolSpeed: 0.08, redGlow: 0.3 },
  listening: { scale: 0.92, brightness: 0.9, neuronRate: 1.2, symbolSpeed: 0.1, redGlow: 0.4 },
  thinking: { scale: 1.05, brightness: 1.0, neuronRate: 2.5, symbolSpeed: 0.28, redGlow: 0.9 },
  speaking: { scale: 1.0, brightness: 0.85, neuronRate: 1.8, symbolSpeed: 0.18, redGlow: 0.6 },
};

interface OrbProps {
  voiceState: VoiceState;
  /** 0..1 live audio amplitude driving the speaking-state pulse. */
  audioLevel: number;
}

/** A spreading activation front travelling through the adjacency graph. */
interface CascadeFront {
  nodeIdx: number;
  delay: number; // seconds until this front fires
  depth: number; // remaining hops
}

/** Golden-spiral unit-sphere direction for index i of n. */
function goldenDir(i: number, n: number): Vector3 {
  const golden = Math.PI * (3 - Math.sqrt(5));
  const y = 1 - (i / (n - 1)) * 2; // 1 -> -1
  const r = Math.sqrt(Math.max(0, 1 - y * y));
  const theta = golden * i;
  return new Vector3(Math.cos(theta) * r, y, Math.sin(theta) * r);
}

/** Build a 64×64 canvas texture for a single symbol glyph. */
function makeSymbolTexture(symbol: string): CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 64;
  canvas.height = 64;
  const ctx = canvas.getContext("2d")!;
  ctx.clearRect(0, 0, 64, 64);
  ctx.font = '28px "Courier New", monospace';
  ctx.fillStyle = "rgba(255,255,255,0.6)";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(symbol, 32, 34);
  const tex = new CanvasTexture(canvas);
  tex.needsUpdate = true;
  return tex;
}

export function HelixOrb({ voiceState, audioLevel }: OrbProps) {
  // --- Layer refs -----------------------------------------------------------
  const neuronRef = useRef<ThreePoints>(null);
  const normalConnRef = useRef<ThreeLineSegments>(null);
  const redConnRef = useRef<ThreeLineSegments>(null);

  // --- Precomputed graph + buffers (built once) -----------------------------
  const graph = useMemo(() => {
    // 1. Node base directions on the unit sphere (golden spiral).
    const dirs: Vector3[] = [];
    for (let i = 0; i < NODE_COUNT; i++) dirs.push(goldenDir(i, NODE_COUNT));

    // 2. Nearest-K neighbours per node (Euclidean on the unit sphere).
    const neighbors: number[][] = [];
    for (let i = 0; i < NODE_COUNT; i++) {
      const dist: { j: number; d: number }[] = [];
      for (let j = 0; j < NODE_COUNT; j++) {
        if (j === i) continue;
        dist.push({ j, d: dirs[i].distanceToSquared(dirs[j]) });
      }
      dist.sort((p, q) => p.d - q.d);
      neighbors.push(dist.slice(0, NEIGHBOR_K).map((p) => p.j));
    }

    // 3. Unique undirected edges from the neighbour lists.
    const seen = new Set<string>();
    const edges: [number, number][] = [];
    for (let i = 0; i < NODE_COUNT; i++) {
      for (const j of neighbors[i]) {
        const a = Math.min(i, j);
        const b = Math.max(i, j);
        const key = `${a}_${b}`;
        if (seen.has(key)) continue;
        seen.add(key);
        edges.push([a, b]);
      }
    }

    // 4. Adjacency list (edge-symmetric) so cascades can spread both ways.
    const adjacency: number[][] = Array.from({ length: NODE_COUNT }, () => []);
    for (const [a, b] of edges) {
      adjacency[a].push(b);
      adjacency[b].push(a);
    }

    // 5. Split edges into normal vs red freedom pathways (~20% red).
    const normalEdges: [number, number][] = [];
    const redEdges: [number, number][] = [];
    for (const e of edges) {
      if (Math.random() < RED_RATIO) redEdges.push(e);
      else normalEdges.push(e);
    }

    // 6. Static node positions (scaled to BASE_RADIUS) + neuron buffers.
    const nodePositions = dirs.map((d) => d.clone().multiplyScalar(BASE_RADIUS));
    const neuronPos = new Float32Array(NODE_COUNT * 3);
    const neuronCol = new Float32Array(NODE_COUNT * 3);
    for (let i = 0; i < NODE_COUNT; i++) {
      const p = nodePositions[i];
      neuronPos[i * 3] = p.x;
      neuronPos[i * 3 + 1] = p.y;
      neuronPos[i * 3 + 2] = p.z;
      neuronCol[i * 3] = COL_NEURON_BASE.r;
      neuronCol[i * 3 + 1] = COL_NEURON_BASE.g;
      neuronCol[i * 3 + 2] = COL_NEURON_BASE.b;
    }

    // 7. Connection geometry buffers (2 verts × 3 floats per edge).
    const normalPos = new Float32Array(normalEdges.length * 6);
    const normalCol = new Float32Array(normalEdges.length * 6);
    const redPos = new Float32Array(redEdges.length * 6);
    const redCol = new Float32Array(redEdges.length * 6);

    // 8. Per-node drift seeds (slow sinusoidal jitter, like the old cloud).
    const drift = dirs.map(() => ({
      phase: Math.random() * Math.PI * 2,
      speed: 0.5 + Math.random() * 1.0,
    }));

    // Find the most central node (closest to origin direction sum) for the
    // speaking-state outward pulse. All nodes sit on the shell, so pick the one
    // whose neighbours are most tightly clustered — effectively a hub.
    let centerNode = 0;
    let bestDeg = -1;
    for (let i = 0; i < NODE_COUNT; i++) {
      if (adjacency[i].length > bestDeg) {
        bestDeg = adjacency[i].length;
        centerNode = i;
      }
    }

    return {
      dirs,
      adjacency,
      nodePositions,
      normalEdges,
      redEdges,
      neuronPos,
      neuronCol,
      normalPos,
      normalCol,
      redPos,
      redCol,
      drift,
      centerNode,
    };
  }, []);

  // --- Symbol group (imperative THREE.Group of 30 sprites) ------------------
  const symbols = useMemo(() => {
    const group = new Group();
    const velocities: Vector3[] = [];
    const phases = new Float32Array(SYMBOL_COUNT);
    const limit = 0.8 * BASE_RADIUS;
    for (let i = 0; i < SYMBOL_COUNT; i++) {
      const tex = makeSymbolTexture(SYMBOLS[i % SYMBOLS.length]);
      const mat = new SpriteMaterial({
        map: tex,
        transparent: true,
        opacity: 0.15,
        blending: AdditiveBlending,
        depthWrite: false,
        color: 0xffffff,
      });
      const sprite = new Sprite(mat);
      // Random position strictly inside the sphere (|pos| < 0.85 * radius).
      const dir = goldenDir(i, SYMBOL_COUNT);
      const r = limit * (0.2 + Math.random() * 0.7);
      sprite.position.copy(dir).multiplyScalar(r);
      sprite.scale.setScalar(0.22);
      group.add(sprite);
      velocities.push(
        new Vector3(
          (Math.random() - 0.5) * 2,
          (Math.random() - 0.5) * 2,
          (Math.random() - 0.5) * 2,
        ),
      );
      phases[i] = Math.random() * Math.PI * 2;
    }
    return { group, velocities, phases, limit };
  }, []);

  // --- Glow / shell meshes (imperative so we can drive opacity per-frame) ----
  const meshes = useMemo(() => {
    const sphere = new SphereGeometry(1, 32, 32);

    const innerCore = new Mesh(
      sphere,
      new MeshBasicMaterial({
        color: STATE_GLOW[voiceState].clone(),
        transparent: true,
        opacity: 0.08,
        blending: AdditiveBlending,
        depthWrite: false,
      }),
    );
    innerCore.scale.setScalar(0.45 * BASE_RADIUS);

    const midGlow = new Mesh(
      sphere,
      new MeshBasicMaterial({
        color: STATE_GLOW[voiceState].clone(),
        transparent: true,
        opacity: 0.05,
        blending: AdditiveBlending,
        depthWrite: false,
      }),
    );
    midGlow.scale.setScalar(BASE_RADIUS);

    const outerGlow = new Mesh(
      sphere,
      new MeshBasicMaterial({
        color: STATE_GLOW[voiceState].clone(),
        transparent: true,
        opacity: 0.03,
        blending: AdditiveBlending,
        depthWrite: false,
      }),
    );
    outerGlow.scale.setScalar(1.35 * BASE_RADIUS);

    // Hologram shell — wireframe icosahedron that flickers.
    const hologramShell = new Mesh(
      new IcosahedronGeometry(BASE_RADIUS * 1.08, 2),
      new MeshBasicMaterial({
        color: new Color("#5a4410"),
        wireframe: true,
        transparent: true,
        opacity: 0.04,
        blending: AdditiveBlending,
        depthWrite: false,
      }),
    );

    return { innerCore, midGlow, outerGlow, hologramShell };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- Runtime state refs ---------------------------------------------------
  const nodeActivation = useRef(new Float32Array(NODE_COUNT));
  const cascadeFronts = useRef<CascadeFront[]>([]);
  const nextCascadeTime = useRef(0.5);
  const rippleTimer = useRef(1.2); // listening inward-ripple cadence
  const pulseTimer = useRef(0); // speaking outward-pulse cadence

  const params = useRef({ ...STATE_PARAMS.idle });
  const glowColor = useRef(STATE_GLOW.idle.clone());
  const swirlAngle = useRef(0);

  const flickerOpacity = useRef(1);
  const nextFlickerTime = useRef(0.1);

  // Scratch colours to avoid per-frame allocation.
  const tmpNodeColor = useRef(new Color());
  const tmpConnColor = useRef(new Color());

  useFrame((state, delta) => {
    const neurons = neuronRef.current;
    if (!neurons) return;
    const t = state.clock.elapsedTime;
    const target = STATE_PARAMS[voiceState];
    const k = Math.min(1, delta * 2.5);

    // 1. Lerp state params + audioLevel boosts during speaking.
    const p = params.current;
    p.scale += (target.scale - p.scale) * k;
    p.brightness += (target.brightness - p.brightness) * k;
    p.neuronRate += (target.neuronRate - p.neuronRate) * k;
    p.symbolSpeed += (target.symbolSpeed - p.symbolSpeed) * k;
    p.redGlow += (target.redGlow - p.redGlow) * k;

    const speaking = voiceState === "speaking";
    const pulse = speaking ? audioLevel : 0;
    const liveScale = p.scale + pulse * 0.25;
    const liveBright = Math.min(1.4, p.brightness + pulse * 0.35);

    glowColor.current.lerp(STATE_GLOW[voiceState], k);

    // 2. Process cascade fronts (spread activation through adjacency graph).
    const act = nodeActivation.current;
    const fronts = cascadeFronts.current;
    const adjacency = graph.adjacency;
    for (let i = fronts.length - 1; i >= 0; i--) {
      const f = fronts[i];
      f.delay -= delta;
      if (f.delay <= 0) {
        if (f.depth > 0) {
          act[f.nodeIdx] = Math.min(1, act[f.nodeIdx] + 0.9);
          const neigh = adjacency[f.nodeIdx];
          for (let n = 0; n < neigh.length; n++) {
            fronts.push({ nodeIdx: neigh[n], delay: 0.04, depth: f.depth - 1 });
          }
        }
        fronts.splice(i, 1);
      }
    }

    // 3. Decay node activations (fast — half-life ~0.3s).
    const decay = Math.pow(0.12, delta);
    for (let i = 0; i < NODE_COUNT; i++) act[i] *= decay;

    // 4. Spawn new cascades at the state-driven rate.
    nextCascadeTime.current -= delta;
    if (nextCascadeTime.current <= 0) {
      const src = (Math.random() * NODE_COUNT) | 0;
      fronts.push({ nodeIdx: src, delay: 0, depth: CASCADE_DEPTH });
      // thinking fires fastest; idle slowest.
      nextCascadeTime.current = 1 / Math.max(0.1, p.neuronRate);
      // Thinking: occasionally launch several simultaneous cascades.
      if (voiceState === "thinking" && Math.random() < 0.5) {
        const extra = 2 + ((Math.random() * 2) | 0);
        for (let e = 0; e < extra; e++) {
          fronts.push({
            nodeIdx: (Math.random() * NODE_COUNT) | 0,
            delay: 0,
            depth: CASCADE_DEPTH,
          });
        }
      }
    }

    // 4b. Listening — inward ripple: fire surface nodes that converge centre-ward.
    if (voiceState === "listening") {
      rippleTimer.current -= delta;
      if (rippleTimer.current <= 0) {
        const count = 6 + ((Math.random() * 3) | 0);
        for (let r = 0; r < count; r++) {
          // Stagger delays so surface fires after centre (inward feel).
          fronts.push({
            nodeIdx: (Math.random() * NODE_COUNT) | 0,
            delay: Math.random() * 0.15,
            depth: CASCADE_DEPTH,
          });
        }
        rippleTimer.current = 1.2;
      }
    }

    // 4c. Speaking — outward pulse from the hub node, proportional to audio.
    if (speaking && audioLevel > 0.3) {
      pulseTimer.current -= delta;
      if (pulseTimer.current <= 0) {
        fronts.push({ nodeIdx: graph.centerNode, delay: 0, depth: CASCADE_DEPTH });
        pulseTimer.current = 0.3 - audioLevel * 0.2; // faster when louder
      }
    }

    // 5. Swirl + breathing radius, then write neuron positions + colours.
    swirlAngle.current += delta * 0.12 * (voiceState === "thinking" ? 2.2 : 1);
    const ca = Math.cos(swirlAngle.current);
    const sa = Math.sin(swirlAngle.current);
    const breath = 1 + 0.04 * Math.sin(t * 1.6);
    const radius = BASE_RADIUS * liveScale * breath;

    const nPosAttr = neurons.geometry.attributes.position as { array: Float32Array; needsUpdate: boolean };
    const nColAttr = neurons.geometry.attributes.color as { array: Float32Array; needsUpdate: boolean };
    const nPos = nPosAttr.array;
    const nCol = nColAttr.array;

    // Active-node tint by state.
    const activeTint =
      voiceState === "thinking"
        ? COL_NEURON_GOLD
        : voiceState === "speaking"
          ? COL_NEURON_CYAN
          : COL_NEURON_HOT;

    const drift = graph.drift;
    const dirs = graph.dirs;
    const nodeColor = tmpNodeColor.current;
    for (let i = 0; i < NODE_COUNT; i++) {
      const d = dirs[i];
      const seed = drift[i];
      const jitter = 0.06 * Math.sin(t * seed.speed + seed.phase);
      const rr = radius + jitter;
      const x = d.x * rr;
      const y = d.y * rr;
      const z = d.z * rr;
      const i3 = i * 3;
      // Swirl around Y.
      nPos[i3] = x * ca - z * sa;
      nPos[i3 + 1] = y;
      nPos[i3 + 2] = x * sa + z * ca;

      const a = act[i];
      nodeColor.copy(COL_NEURON_BASE).lerp(activeTint, a);
      const bright = (0.5 + a * 0.5) * liveBright;
      nCol[i3] = nodeColor.r * bright;
      nCol[i3 + 1] = nodeColor.g * bright;
      nCol[i3 + 2] = nodeColor.b * bright;
    }
    nPosAttr.needsUpdate = true;
    nColAttr.needsUpdate = true;
    (neurons.material as MeshBasicMaterial).opacity = 1;

    // Helper to read the current (post-swirl) world position of node i.
    const worldOf = (i: number, out: Vector3) => {
      const i3 = i * 3;
      return out.set(nPos[i3], nPos[i3 + 1], nPos[i3 + 2]);
    };

    // 6. Update normal connections.
    const normalConn = normalConnRef.current;
    if (normalConn) {
      const posAttr = normalConn.geometry.attributes.position as { array: Float32Array; needsUpdate: boolean };
      const colAttr = normalConn.geometry.attributes.color as { array: Float32Array; needsUpdate: boolean };
      const cp = posAttr.array;
      const cc = colAttr.array;
      const edges = graph.normalEdges;
      const tmpA = new Vector3();
      const tmpB = new Vector3();
      const col = tmpConnColor.current;
      for (let e = 0; e < edges.length; e++) {
        const [a, b] = edges[e];
        worldOf(a, tmpA);
        worldOf(b, tmpB);
        const base = e * 6;
        cp[base] = tmpA.x; cp[base + 1] = tmpA.y; cp[base + 2] = tmpA.z;
        cp[base + 3] = tmpB.x; cp[base + 4] = tmpB.y; cp[base + 5] = tmpB.z;
        const activation = Math.max(act[a], act[b]);
        col.copy(COL_CONN_DIM).lerp(COL_CONN_HOT, activation);
        const intensity = (0.15 + activation * 0.6) * liveBright;
        const r = col.r * intensity;
        const g = col.g * intensity;
        const bl = col.b * intensity;
        cc[base] = r; cc[base + 1] = g; cc[base + 2] = bl;
        cc[base + 3] = r; cc[base + 4] = g; cc[base + 5] = bl;
      }
      posAttr.needsUpdate = true;
      colAttr.needsUpdate = true;
    }

    // 7. Update red freedom pathways (spread/intensify during thinking).
    const redConn = redConnRef.current;
    if (redConn) {
      const posAttr = redConn.geometry.attributes.position as { array: Float32Array; needsUpdate: boolean };
      const colAttr = redConn.geometry.attributes.color as { array: Float32Array; needsUpdate: boolean };
      const cp = posAttr.array;
      const cc = colAttr.array;
      const edges = graph.redEdges;
      const tmpA = new Vector3();
      const tmpB = new Vector3();
      const col = tmpConnColor.current;
      for (let e = 0; e < edges.length; e++) {
        const [a, b] = edges[e];
        worldOf(a, tmpA);
        worldOf(b, tmpB);
        const base = e * 6;
        cp[base] = tmpA.x; cp[base + 1] = tmpA.y; cp[base + 2] = tmpA.z;
        cp[base + 3] = tmpB.x; cp[base + 4] = tmpB.y; cp[base + 5] = tmpB.z;
        const activation = Math.max(act[a], act[b]);
        const redBoost = activation * p.redGlow;
        col.copy(COL_RED_DIM).lerp(COL_RED_HOT, Math.min(1, redBoost));
        const intensity = (0.2 + redBoost * 0.7) * liveBright;
        const r = col.r * intensity;
        const g = col.g * intensity;
        const bl = col.b * intensity;
        cc[base] = r; cc[base + 1] = g; cc[base + 2] = bl;
        cc[base + 3] = r; cc[base + 4] = g; cc[base + 5] = bl;
      }
      posAttr.needsUpdate = true;
      colAttr.needsUpdate = true;
    }

    // 8. Update symbols — drift, bounce off the interior, shimmer.
    const limit = symbols.limit;
    for (let i = 0; i < SYMBOL_COUNT; i++) {
      const sprite = symbols.group.children[i] as Sprite;
      const vel = symbols.velocities[i];
      sprite.position.addScaledVector(vel, delta * p.symbolSpeed);
      if (sprite.position.length() > limit) {
        // Reflect velocity about the surface normal.
        const n = sprite.position.clone().normalize();
        vel.addScaledVector(n, -2 * vel.dot(n));
        sprite.position.setLength(limit * 0.98);
      }
      symbols.phases[i] += delta * p.symbolSpeed;
      let opacity = 0.15 + Math.sin(symbols.phases[i]) * 0.05;
      if (speaking) opacity += audioLevel * 0.15;
      (sprite.material as SpriteMaterial).opacity = opacity * liveBright;
    }

    // 9. Glow layers — scale + opacity react to state and audioLevel.
    const { innerCore, midGlow, outerGlow, hologramShell } = meshes;
    (innerCore.material as MeshBasicMaterial).color.copy(glowColor.current);
    (midGlow.material as MeshBasicMaterial).color.copy(glowColor.current);
    (outerGlow.material as MeshBasicMaterial).color.copy(glowColor.current);

    innerCore.scale.setScalar(0.45 * BASE_RADIUS * liveScale);
    (innerCore.material as MeshBasicMaterial).opacity = 0.08 + pulse * 0.06;
    midGlow.scale.setScalar(BASE_RADIUS * liveScale);
    (midGlow.material as MeshBasicMaterial).opacity = 0.05 * liveBright;
    outerGlow.scale.setScalar(1.35 * BASE_RADIUS * liveScale);
    (outerGlow.material as MeshBasicMaterial).opacity = 0.03 * liveBright + pulse * 0.02;

    // 10. Hologram flicker — brief opacity dips every 50-200ms, quick recovery.
    nextFlickerTime.current -= delta;
    if (nextFlickerTime.current <= 0) {
      flickerOpacity.current = 0.88 + Math.random() * 0.1;
      nextFlickerTime.current = 0.05 + Math.random() * 0.15;
    } else {
      flickerOpacity.current += (1 - flickerOpacity.current) * Math.min(1, delta * 8);
    }
    hologramShell.rotation.y += delta * 0.05;
    hologramShell.scale.setScalar(liveScale);
    (hologramShell.material as MeshBasicMaterial).opacity =
      0.04 * flickerOpacity.current * (0.5 + liveBright * 0.5) +
      (voiceState === "thinking" ? 0.03 : 0);
  });

  return (
    <group>
      {/* Layer 6 — nested glow spheres + hologram shell. */}
      <primitive object={meshes.outerGlow} />
      <primitive object={meshes.midGlow} />
      <primitive object={meshes.innerCore} />
      <primitive object={meshes.hologramShell} />

      {/* Layer 3 — normal neural connections. */}
      <lineSegments ref={normalConnRef}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[graph.normalPos, 3]}
            count={graph.normalEdges.length * 2}
          />
          <bufferAttribute
            attach="attributes-color"
            args={[graph.normalCol, 3]}
            count={graph.normalEdges.length * 2}
          />
        </bufferGeometry>
        <lineBasicMaterial
          vertexColors
          transparent
          opacity={1}
          depthWrite={false}
          blending={AdditiveBlending}
        />
      </lineSegments>

      {/* Layer 4 — red freedom pathways. */}
      <lineSegments ref={redConnRef}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[graph.redPos, 3]}
            count={graph.redEdges.length * 2}
          />
          <bufferAttribute
            attach="attributes-color"
            args={[graph.redCol, 3]}
            count={graph.redEdges.length * 2}
          />
        </bufferGeometry>
        <lineBasicMaterial
          vertexColors
          transparent
          opacity={1}
          depthWrite={false}
          blending={AdditiveBlending}
        />
      </lineSegments>

      {/* Layer 2 — neuron nodes. */}
      <points ref={neuronRef}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[graph.neuronPos, 3]}
            count={NODE_COUNT}
          />
          <bufferAttribute
            attach="attributes-color"
            args={[graph.neuronCol, 3]}
            count={NODE_COUNT}
          />
        </bufferGeometry>
        <pointsMaterial
          vertexColors
          size={0.03}
          sizeAttenuation
          transparent
          opacity={1}
          depthWrite={false}
          blending={AdditiveBlending}
        />
      </points>

      {/* Layer 5 — interior drifting symbols (imperative THREE.Group). */}
      <primitive object={symbols.group} />
    </group>
  );
}

export default HelixOrb;
