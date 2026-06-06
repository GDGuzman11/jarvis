/**
 * JarvisOrb — an ethereal "sand" particle orb rendered with React Three Fiber.
 *
 * 2500 additively-blended points sit on/around a sphere. Per-particle motion is
 * a cheap time-based sinusoidal noise drift (no external noise lib). Voice state
 * (from the Zustand store) drives colour, swirl speed, orbit tightness and — in
 * the speaking state — an amplitude-driven outward "explosion" pulse fed by the
 * live `audioLevel` (0..1, broadcast by the backend every 50ms during TTS).
 *
 * Layered on top is the Neural Link system: gentle synaptic arcs that travel
 * between surface nodes during idle/speaking, and sharp jagged discharge arcs
 * that crackle across the surface during thinking/listening. A fraction of
 * discharge arcs are "memory" arcs that bleed from gold through purple to white
 * as they decay.
 *
 * All transitions are lerped inside `useFrame` so colour/behaviour morph
 * smoothly between states rather than snapping.
 */

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import {
  AdditiveBlending,
  BufferAttribute,
  BufferGeometry,
  Color,
  Line,
  LineBasicMaterial,
  LineSegments,
  Points,
  QuadraticBezierCurve3,
  Vector3,
  type Points as ThreePoints,
  type PointsMaterial as ThreePointsMaterial,
} from "three";
import type { VoiceState } from "../lib/types";

const PARTICLE_COUNT = 2500;
const BASE_RADIUS = 1.2;

// --- Neural Link tuning -----------------------------------------------------
const NODE_COUNT = 14; // invisible synaptic nodes on the sphere surface
const ARC_POOL = 5; // synaptic arc slots (idle / speaking)
const ARC_SEGMENTS = 24; // sampled points per synaptic bezier curve
const ARC_LIFETIME = 0.8; // seconds for a synaptic arc envelope
const IMPULSE_DURATION = 0.2; // seconds for the impulse dot to traverse an arc
const DISCHARGE_POOL = 6; // jagged discharge slots (thinking / listening)
const DISCHARGE_MAX_SEG = 7; // max polyline segments per discharge arc
const DISCHARGE_VERTS = DISCHARGE_MAX_SEG + 1; // vertices per discharge arc

const COL_CYAN = new Color("#00d4ff");
const COL_GOLD = new Color("#ffb800");
const COL_PURPLE = new Color("#8b5cf6");
const COL_WHITE = new Color("#ffffff");

const STATE_COLOR: Record<VoiceState, string> = {
  idle: "#00d4ff", // soft electric blue
  listening: "#00ffff", // cyan
  thinking: "#ffb800", // gold
  speaking: "#00ffff", // bright cyan
};

/** Per-state behaviour knobs the animation lerps toward. */
const STATE_PARAMS: Record<
  VoiceState,
  { swirl: number; tightness: number; drift: number; breathe: number }
> = {
  // swirl: rotation speed · tightness: how close to the shell (1 = on shell)
  // drift: sinusoidal jitter amplitude · breathe: idle breathing depth
  idle: { swirl: 0.12, tightness: 1.0, drift: 0.16, breathe: 0.05 },
  listening: { swirl: 0.3, tightness: 0.96, drift: 0.18, breathe: 0.04 },
  thinking: { swirl: 0.7, tightness: 0.82, drift: 0.1, breathe: 0.03 },
  speaking: { swirl: 0.45, tightness: 1.04, drift: 0.22, breathe: 0.04 },
};

interface OrbProps {
  voiceState: VoiceState;
  /** 0..1 live audio amplitude driving the speaking-state explosion radius. */
  audioLevel: number;
}

interface ParticleSeed {
  /** Unit-sphere base direction. */
  bx: number;
  by: number;
  bz: number;
  /** Per-particle phase offsets so drift is incoherent across the cloud. */
  phase: number;
  speed: number;
}

/** A single synaptic arc slot (idle / speaking). */
interface ArcSlot {
  active: boolean;
  age: number; // seconds since spawn
  curve: QuadraticBezierCurve3 | null;
  /** Sampled curve points, refreshed on spawn. */
  samples: Vector3[];
  impulseProgress: number; // 0..1 along the curve
}

/** A single jagged discharge slot (thinking / listening). */
interface DischargeSlot {
  active: boolean;
  age: number;
  lifetime: number;
  memoryArc: boolean;
  /** Flat per-vertex world positions (DISCHARGE_VERTS points). */
  verts: Vector3[];
}

/** Sample a quadratic bezier into `count` Vector3 points. */
function sampleCurve(curve: QuadraticBezierCurve3, count: number): Vector3[] {
  const out: Vector3[] = [];
  for (let i = 0; i < count; i++) out.push(curve.getPoint(i / (count - 1)));
  return out;
}

/** Random unit-sphere direction. */
function randomDir(): Vector3 {
  const u = Math.random() * 2 - 1;
  const phi = Math.random() * Math.PI * 2;
  const r = Math.sqrt(Math.max(0, 1 - u * u));
  return new Vector3(r * Math.cos(phi), u, r * Math.sin(phi));
}

export function JarvisOrb({ voiceState, audioLevel }: OrbProps) {
  const pointsRef = useRef<ThreePoints>(null);

  // Neural Link impulse-dot ref — its position buffer is written per-frame.
  const impulseRef = useRef<Points | null>(null);

  // 14 invisible synaptic nodes evenly distributed on the surface sphere.
  const nodes = useMemo(() => {
    const out: Vector3[] = [];
    const golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < NODE_COUNT; i++) {
      const y = 1 - (i / (NODE_COUNT - 1)) * 2;
      const r = Math.sqrt(Math.max(0, 1 - y * y));
      const theta = golden * i;
      out.push(
        new Vector3(Math.cos(theta) * r, y, Math.sin(theta) * r).multiplyScalar(
          BASE_RADIUS,
        ),
      );
    }
    return out;
  }, []);

  // Synaptic arc pool (idle / speaking).
  const arcs = useRef<ArcSlot[]>(
    Array.from({ length: ARC_POOL }, () => ({
      active: false,
      age: 0,
      curve: null,
      samples: [],
      impulseProgress: 0,
    })),
  );
  const arcSpawnTimer = useRef(0.6);

  // Impulse-dot position buffer (one point per arc slot, parked off-screen).
  const impulsePositions = useMemo(
    () => new Float32Array(ARC_POOL * 3).fill(10_000),
    [],
  );

  // Per-arc reusable geometries, materials and Line objects so each arc owns
  // its own buffer. Built once and updated imperatively in useFrame.
  const arcGeometries = useMemo(
    () =>
      Array.from({ length: ARC_POOL }, () => {
        const g = new BufferGeometry();
        g.setAttribute(
          "position",
          new BufferAttribute(new Float32Array(ARC_SEGMENTS * 3), 3),
        );
        return g;
      }),
    [],
  );
  const arcMaterials = useMemo(
    () =>
      Array.from(
        { length: ARC_POOL },
        () =>
          new LineBasicMaterial({
            color: 0x00d4ff,
            transparent: true,
            opacity: 0,
            blending: AdditiveBlending,
            depthWrite: false,
          }),
      ),
    [],
  );
  const arcLines = useMemo(
    () => arcGeometries.map((g, i) => new Line(g, arcMaterials[i])),
    [arcGeometries, arcMaterials],
  );

  // Discharge pool (thinking / listening) — one shared LineSegments buffer.
  const discharges = useRef<DischargeSlot[]>(
    Array.from({ length: DISCHARGE_POOL }, () => ({
      active: false,
      age: 0,
      lifetime: 0,
      memoryArc: false,
      verts: Array.from({ length: DISCHARGE_VERTS }, () => new Vector3()),
    })),
  );
  const dischargeSpawnTimer = useRef(0.2);

  // LineSegments needs 2 vertices per segment; DISCHARGE_VERTS-1 segments/slot.
  const dischargeGeometry = useMemo(() => {
    const segPerSlot = DISCHARGE_VERTS - 1;
    const vertCount = DISCHARGE_POOL * segPerSlot * 2;
    const g = new BufferGeometry();
    g.setAttribute(
      "position",
      new BufferAttribute(new Float32Array(vertCount * 3), 3),
    );
    g.setAttribute(
      "color",
      new BufferAttribute(new Float32Array(vertCount * 3), 3),
    );
    return g;
  }, []);
  const dischargeObject = useMemo(
    () =>
      new LineSegments(
        dischargeGeometry,
        new LineBasicMaterial({
          vertexColors: true,
          transparent: true,
          opacity: 1,
          blending: AdditiveBlending,
          depthWrite: false,
        }),
      ),
    [dischargeGeometry],
  );

  // Seed the cloud once: evenly distribute directions on the unit sphere via the
  // golden-spiral method, then give each particle a random phase/speed so the
  // sinusoidal drift looks organic rather than synchronised.
  const { positions, seeds } = useMemo(() => {
    const positions = new Float32Array(PARTICLE_COUNT * 3);
    const seeds: ParticleSeed[] = new Array(PARTICLE_COUNT);
    const golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const y = 1 - (i / (PARTICLE_COUNT - 1)) * 2; // 1 -> -1
      const r = Math.sqrt(Math.max(0, 1 - y * y));
      const theta = golden * i;
      const bx = Math.cos(theta) * r;
      const by = y;
      const bz = Math.sin(theta) * r;
      const i3 = i * 3;
      positions[i3] = bx * BASE_RADIUS;
      positions[i3 + 1] = by * BASE_RADIUS;
      positions[i3 + 2] = bz * BASE_RADIUS;
      seeds[i] = {
        bx,
        by,
        bz,
        phase: Math.random() * Math.PI * 2,
        speed: 0.5 + Math.random() * 1.5,
      };
    }
    return { positions, seeds };
  }, []);

  // Lerped runtime values so state changes morph smoothly.
  const colorRef = useRef(new Color(STATE_COLOR[voiceState]));
  const targetColor = useMemo(
    () => new Color(STATE_COLOR[voiceState]),
    [voiceState],
  );
  const params = useRef({ ...STATE_PARAMS.idle });
  const swirlAngle = useRef(0);

  useFrame((state, delta) => {
    const pts = pointsRef.current;
    if (!pts) return;
    const t = state.clock.elapsedTime;
    const target = STATE_PARAMS[voiceState];
    const k = Math.min(1, delta * 3);

    // Lerp behaviour params toward the active state's targets.
    params.current.swirl += (target.swirl - params.current.swirl) * k;
    params.current.tightness += (target.tightness - params.current.tightness) * k;
    params.current.drift += (target.drift - params.current.drift) * k;
    params.current.breathe += (target.breathe - params.current.breathe) * k;

    // Lerp colour and push it into the material.
    colorRef.current.lerp(targetColor, k);
    const mat = pts.material as ThreePointsMaterial;
    mat.color.copy(colorRef.current);

    // audioLevel only affects size during the speaking state (lip-sync pulse).
    const pulse = voiceState === "speaking" ? audioLevel : 0;
    mat.opacity = 0.55 + pulse * 0.45;

    const { swirl, tightness, drift, breathe } = params.current;
    swirlAngle.current += delta * swirl;
    const ca = Math.cos(swirlAngle.current);
    const sa = Math.sin(swirlAngle.current);

    // Breathing + amplitude-driven explosion radius. During speaking the cloud
    // expands outward on each amplitude pulse; otherwise audioLevel is ignored.
    const breath = 1 + breathe * Math.sin(t * 1.6);
    const radius = BASE_RADIUS * tightness * breath * (1 + pulse * 0.6);

    const arr = pts.geometry.attributes.position as {
      array: Float32Array;
      needsUpdate: boolean;
    };
    const pos = arr.array;
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const s = seeds[i];
      // Sinusoidal noise drift along the base direction's tangent-ish space.
      const n = drift * Math.sin(t * s.speed + s.phase);
      const dx = s.bx * (radius + n);
      const dy = s.by * (radius + n);
      const dz = s.bz * (radius + n);
      // Swirl: rotate around the Y axis so the shell rotates as a whole.
      const i3 = i * 3;
      pos[i3] = dx * ca - dz * sa;
      pos[i3 + 1] = dy;
      pos[i3 + 2] = dx * sa + dz * ca;
    }
    arr.needsUpdate = true;

    const synapticActive = voiceState === "idle" || voiceState === "speaking";
    const dischargeActive =
      voiceState === "thinking" || voiceState === "listening";

    updateSynapticArcs(delta, synapticActive);
    updateDischargeArcs(delta, dischargeActive);
  });

  // --- Synaptic arcs (idle / speaking) -------------------------------------
  function updateSynapticArcs(delta: number, canSpawn: boolean) {
    const slots = arcs.current;
    const lines = arcLines;
    const impulse = impulseRef.current;
    const impulsePos = impulse
      ? (impulse.geometry.attributes.position as {
          array: Float32Array;
          needsUpdate: boolean;
        })
      : null;

    // Spawn cadence: roughly one arc every ~1.5–4s while a slot is free.
    if (canSpawn) {
      arcSpawnTimer.current -= delta;
      if (arcSpawnTimer.current <= 0) {
        const free = slots.find((s) => !s.active);
        if (free) {
          let a = (Math.random() * NODE_COUNT) | 0;
          let b = (Math.random() * NODE_COUNT) | 0;
          if (b === a) b = (b + 1) % NODE_COUNT;
          const from = nodes[a];
          const to = nodes[b];
          const mid = from.clone().add(to).multiplyScalar(0.5);
          // Bow the control point 0.4 units outward along the surface normal.
          const ctrl = mid
            .clone()
            .add(mid.clone().normalize().multiplyScalar(0.4));
          const curve = new QuadraticBezierCurve3(from.clone(), ctrl, to.clone());
          free.active = true;
          free.age = 0;
          free.impulseProgress = 0;
          free.curve = curve;
          free.samples = sampleCurve(curve, ARC_SEGMENTS);
        }
        arcSpawnTimer.current = 1.5 + Math.random() * 2.5;
      }
    }

    for (let i = 0; i < slots.length; i++) {
      const slot = slots[i];
      const geom = arcGeometries[i];
      const matObj = arcMaterials[i];
      const lineObj = lines[i];
      const posAttr = geom.attributes.position as BufferAttribute;
      const arrPos = posAttr.array as Float32Array;

      if (!slot.active) {
        matObj.opacity = 0;
        if (impulsePos) {
          impulsePos.array[i * 3] = 10_000;
          impulsePos.array[i * 3 + 1] = 10_000;
          impulsePos.array[i * 3 + 2] = 10_000;
        }
        continue;
      }

      slot.age += delta;
      if (slot.age >= ARC_LIFETIME) {
        slot.active = false;
        matObj.opacity = 0;
        if (impulsePos) {
          impulsePos.array[i * 3] = 10_000;
          impulsePos.array[i * 3 + 1] = 10_000;
          impulsePos.array[i * 3 + 2] = 10_000;
        }
        continue;
      }

      // Write the sampled curve into the line buffer.
      for (let s = 0; s < ARC_SEGMENTS; s++) {
        const p = slot.samples[s];
        const s3 = s * 3;
        arrPos[s3] = p.x;
        arrPos[s3 + 1] = p.y;
        arrPos[s3 + 2] = p.z;
      }
      posAttr.needsUpdate = true;
      geom.computeBoundingSphere();

      // sin envelope over the lifetime.
      const env = Math.sin((slot.age / ARC_LIFETIME) * Math.PI);
      matObj.opacity = env * 0.85;
      if (lineObj) lineObj.visible = true;

      // Impulse dot traverses the curve in ~0.2s then parks.
      if (impulsePos && slot.curve) {
        slot.impulseProgress = Math.min(1, slot.age / IMPULSE_DURATION);
        if (slot.impulseProgress < 1) {
          const p = slot.curve.getPoint(slot.impulseProgress);
          impulsePos.array[i * 3] = p.x;
          impulsePos.array[i * 3 + 1] = p.y;
          impulsePos.array[i * 3 + 2] = p.z;
        } else {
          impulsePos.array[i * 3] = 10_000;
          impulsePos.array[i * 3 + 1] = 10_000;
          impulsePos.array[i * 3 + 2] = 10_000;
        }
      }
    }

    if (impulsePos) impulsePos.needsUpdate = true;
  }

  // --- Discharge arcs (thinking / listening) -------------------------------
  function updateDischargeArcs(delta: number, canSpawn: boolean) {
    const slots = discharges.current;
    const seg = dischargeGeometry;
    const posAttr = seg.attributes.position as BufferAttribute;
    const colAttr = seg.attributes.color as BufferAttribute;
    const posArr = posAttr.array as Float32Array;
    const colArr = colArr_(colAttr);
    const segPerSlot = DISCHARGE_VERTS - 1;
    const baseColor = voiceState === "thinking" ? COL_GOLD : COL_CYAN;

    if (canSpawn) {
      dischargeSpawnTimer.current -= delta;
      if (dischargeSpawnTimer.current <= 0) {
        const free = slots.find((s) => !s.active);
        if (free) spawnDischarge(free);
        dischargeSpawnTimer.current = 0.15 + Math.random() * 0.25;
      }
    }

    const tmpColor = new Color();
    for (let i = 0; i < slots.length; i++) {
      const slot = slots[i];
      const slotVertBase = i * segPerSlot * 2; // vertex index for this slot

      if (!slot.active) {
        // Collapse this slot's segment vertices to a degenerate point.
        for (let v = 0; v < segPerSlot * 2; v++) {
          const idx = (slotVertBase + v) * 3;
          posArr[idx] = 10_000;
          posArr[idx + 1] = 10_000;
          posArr[idx + 2] = 10_000;
        }
        continue;
      }

      slot.age += delta;
      const life = slot.age / slot.lifetime; // 0..1
      if (life >= 1) {
        slot.active = false;
        for (let v = 0; v < segPerSlot * 2; v++) {
          const idx = (slotVertBase + v) * 3;
          posArr[idx] = 10_000;
          posArr[idx + 1] = 10_000;
          posArr[idx + 2] = 10_000;
        }
        continue;
      }

      const fade = 1 - life; // linear fade out
      // Memory arcs lerp gold -> purple -> white as opacity decays 1 -> 0.
      if (slot.memoryArc) {
        if (fade > 0.5) {
          // 1.0 -> 0.5 maps gold -> purple
          tmpColor.copy(COL_GOLD).lerp(COL_PURPLE, (1 - fade) / 0.5);
        } else {
          // 0.5 -> 0.0 maps purple -> white
          tmpColor.copy(COL_PURPLE).lerp(COL_WHITE, (0.5 - fade) / 0.5);
        }
      } else {
        tmpColor.copy(baseColor);
      }
      const r = tmpColor.r * fade;
      const g = tmpColor.g * fade;
      const b = tmpColor.b * fade;

      // Emit segPerSlot segments (2 verts each) from the polyline vertices.
      for (let s = 0; s < segPerSlot; s++) {
        const a = slot.verts[s];
        const c = slot.verts[s + 1];
        const vBaseA = (slotVertBase + s * 2) * 3;
        const vBaseB = (slotVertBase + s * 2 + 1) * 3;
        posArr[vBaseA] = a.x;
        posArr[vBaseA + 1] = a.y;
        posArr[vBaseA + 2] = a.z;
        posArr[vBaseB] = c.x;
        posArr[vBaseB + 1] = c.y;
        posArr[vBaseB + 2] = c.z;
        colArr[vBaseA] = r;
        colArr[vBaseA + 1] = g;
        colArr[vBaseA + 2] = b;
        colArr[vBaseB] = r;
        colArr[vBaseB + 1] = g;
        colArr[vBaseB + 2] = b;
      }
    }

    posAttr.needsUpdate = true;
    colAttr.needsUpdate = true;
  }

  function spawnDischarge(slot: DischargeSlot) {
    const a = randomDir().multiplyScalar(BASE_RADIUS);
    const b = randomDir().multiplyScalar(BASE_RADIUS);
    const segCount = 5 + ((Math.random() * 3) | 0); // 5..7 segments
    const used = Math.min(segCount, DISCHARGE_VERTS - 1);
    const dir = b.clone().sub(a);
    // Build a perpendicular basis for the jitter.
    const perp = new Vector3(-dir.y, dir.x, 0);
    if (perp.lengthSq() < 1e-4) perp.set(0, -dir.z, dir.y);
    perp.normalize();
    const perp2 = dir.clone().normalize().cross(perp).normalize();

    for (let v = 0; v <= DISCHARGE_VERTS - 1; v++) {
      const target = slot.verts[v];
      if (v > used) {
        // Collapse unused tail vertices onto the endpoint.
        target.copy(b);
        continue;
      }
      const f = v / used;
      target.copy(a).lerp(b, f);
      if (v !== 0 && v !== used) {
        const j1 = (Math.random() - 0.5) * 0.5; // ±0.25
        const j2 = (Math.random() - 0.5) * 0.5;
        target.addScaledVector(perp, j1);
        target.addScaledVector(perp2, j2);
      }
    }

    slot.active = true;
    slot.age = 0;
    slot.lifetime = 0.1 + Math.random() * 0.15; // 0.1..0.25s
    slot.memoryArc = Math.random() < 0.25;
  }

  return (
    <group>
      <points ref={pointsRef}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[positions, 3]}
            count={PARTICLE_COUNT}
          />
        </bufferGeometry>
        <pointsMaterial
          size={0.035}
          sizeAttenuation
          color={STATE_COLOR[voiceState]}
          transparent
          opacity={0.6}
          depthWrite={false}
          blending={AdditiveBlending}
        />
      </points>

      {/* Neural Link — synaptic arcs (idle / speaking). */}
      {arcLines.map((line, i) => (
        <primitive key={`arc-${i}`} object={line} />
      ))}

      {/* Synaptic impulse dots — one per arc slot, parked off-screen idle. */}
      <points ref={impulseRef}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[impulsePositions, 3]}
            count={ARC_POOL}
          />
        </bufferGeometry>
        <pointsMaterial
          size={0.06}
          sizeAttenuation
          color="#ffffff"
          transparent
          opacity={0.95}
          depthWrite={false}
          blending={AdditiveBlending}
        />
      </points>

      {/* Neural Link — jagged discharge arcs (thinking / listening). */}
      <primitive object={dischargeObject} />

      {/* Faint inner core for depth — additive so it reads as a glow centre. */}
      <mesh scale={0.5}>
        <sphereGeometry args={[1, 24, 24]} />
        <meshBasicMaterial
          color={STATE_COLOR[voiceState]}
          transparent
          opacity={0.06}
          blending={AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
    </group>
  );
}

/** Narrow a BufferAttribute's array to a writable Float32Array. */
function colArr_(attr: BufferAttribute): Float32Array {
  return attr.array as Float32Array;
}

export default JarvisOrb;
