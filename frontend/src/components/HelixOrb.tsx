/**
 * HelixOrb — Helix's identity symbol. PURE SYMBOLISM, never a data view.
 *
 * A cinematic 3D DOUBLE HELIX (the name Helix = a double helix):
 *
 *   1. TWO STRANDS — two intertwined helical ribbons running up the Y axis,
 *      180° out of phase. Each strand is a smooth TubeGeometry swept along a
 *      CatmullRom curve of sampled helix points (continuous tube, not a chain
 *      of primitives). Strand A is soft white, strand B is gold.
 *
 *   2. RUNGS — thin cylinders bridging the two strands at regular intervals
 *      (DNA base pairs), so it unmistakably reads as a double helix.
 *
 *   3. SLOW SPIN — the whole helix group turns slowly around its Y axis. The
 *      group is given a slight cinematic tilt for depth.
 *
 *   4. FREE-FLOWING DOTS — ~50 small shaded spheres drift on their own around
 *      the helix (per-dot orbital motion + smooth noise wobble — alive, not a
 *      rigid shell). Each dot has a thin faint connector line to an assigned
 *      point on the helix; the line follows both the drifting dot and the
 *      spinning helix. Dots + lines update via typed arrays in one useFrame
 *      (one InstancedMesh + one LineSegments — no per-dot React objects).
 *
 *   5. LIGHTING — soft ambient + key + gold rim light give the tubes and rungs
 *      dimensional shading (lit MeshStandardMaterial, low roughness). NO glow,
 *      NO bloom, NO additive halos — clean and premium.
 *
 * Voice reactivity is preserved via the unchanged `HelixOrb({ voiceState,
 * audioLevel })` signature; per-state knobs are lerped toward each frame and
 * stay deliberately calm/cinematic:
 *   idle      — slow spin + gentle dot drift.
 *   listening — slightly brighter + a touch more drift.
 *   thinking  — faster spin.
 *   speaking  — audioLevel adds a subtle spin + dot-energy boost.
 *
 * Palette: gold/white only. No cyan, no data fetching, no new dependencies.
 */

import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import {
  BufferGeometry,
  CatmullRomCurve3,
  Color,
  DirectionalLight,
  Float32BufferAttribute,
  Group,
  InstancedMesh,
  LineSegments,
  Object3D,
  Quaternion,
  TubeGeometry,
  Vector3,
} from "three";
import type { VoiceState } from "../lib/types";

// --- Helix geometry constants ----------------------------------------------
const TURNS = 3.4; // number of full turns of each strand
const RADIUS = 0.85; // helix radius
const HEIGHT = 2.7; // total vertical span
const STRAND_SAMPLES = 220; // curve samples per strand (smooth tube)
const STRAND_TUBE = 0.045; // strand ribbon thickness
const RUNG_COUNT = 16; // DNA base pairs
const DOT_COUNT = 50; // free-flowing dots

const WHITE = "#eef2f7";
const GOLD = "#ffc247";
const GOLD_HI = "#ffe9a8";
const AQUA = "#3fe3d0"; // gyroscope orbital rings

const TWO_PI = Math.PI * 2;

/** Point on a strand at fractional position f (0..1) with the given phase. */
function helixPoint(f: number, phase: number): Vector3 {
  const theta = f * TURNS * TWO_PI + phase;
  return new Vector3(
    RADIUS * Math.cos(theta),
    (f - 0.5) * HEIGHT,
    RADIUS * Math.sin(theta),
  );
}

/** Build one strand as a smooth tube swept along a CatmullRom helix curve. */
function buildStrand(phase: number): TubeGeometry {
  const pts: Vector3[] = [];
  for (let i = 0; i <= STRAND_SAMPLES; i++) {
    pts.push(helixPoint(i / STRAND_SAMPLES, phase));
  }
  const curve = new CatmullRomCurve3(pts, false, "catmullrom", 0.5);
  return new TubeGeometry(curve, STRAND_SAMPLES, STRAND_TUBE, 14, false);
}

/** Per-state behaviour knobs the animation lerps toward each frame. */
const STATE_PARAMS: Record<
  VoiceState,
  { spin: number; drift: number; bright: number }
> = {
  idle: { spin: 0.16, drift: 0.85, bright: 1.0 },
  listening: { spin: 0.22, drift: 1.15, bright: 1.14 },
  thinking: { spin: 0.55, drift: 1.25, bright: 1.08 },
  speaking: { spin: 0.2, drift: 1.0, bright: 1.06 },
};

interface OrbProps {
  voiceState: VoiceState;
  /** 0..1 live audio amplitude driving the speaking-state pulse. */
  audioLevel: number;
}

/** Static per-dot motion descriptors (computed once). */
interface DotData {
  baseAngle: number;
  baseRad: number;
  baseY: number;
  angSpeed: number;
  f1: number; p1: number; // angular wobble
  f2: number; p2: number; // radial wobble
  f3: number; p3: number; // vertical wobble
  scale: number;
  local: Vector3; // assigned attachment point in helix-local space
}

export function HelixOrb({ voiceState, audioLevel }: OrbProps) {
  // --- Strand tube geometries (built once) ---------------------------------
  const strandA = useMemo(() => buildStrand(0), []);
  const strandB = useMemo(() => buildStrand(Math.PI), []);

  // --- Rungs (DNA base pairs) — static transforms, built once --------------
  const rungs = useMemo(() => {
    const up = new Vector3(0, 1, 0);
    const out: {
      position: [number, number, number];
      quaternion: [number, number, number, number];
      length: number;
      gold: boolean;
    }[] = [];
    for (let i = 0; i < RUNG_COUNT; i++) {
      const f = (i + 0.5) / RUNG_COUNT;
      const a = helixPoint(f, 0);
      const b = helixPoint(f, Math.PI);
      const mid = a.clone().add(b).multiplyScalar(0.5);
      const dir = b.clone().sub(a);
      const length = dir.length();
      dir.normalize();
      const q = new Quaternion().setFromUnitVectors(up, dir);
      out.push({
        position: [mid.x, mid.y, mid.z],
        quaternion: [q.x, q.y, q.z, q.w],
        length,
        gold: i % 2 === 0,
      });
    }
    return out;
  }, []);

  // --- Dots: static motion data + typed buffers for instances & lines ------
  const dots = useMemo<DotData[]>(() => {
    const arr: DotData[] = [];
    for (let i = 0; i < DOT_COUNT; i++) {
      const f = Math.random();
      const phase = Math.random() < 0.5 ? 0 : Math.PI;
      const local = helixPoint(f, phase);
      const baseAngle = f * TURNS * TWO_PI + phase + (Math.random() - 0.5) * 1.1;
      arr.push({
        baseAngle,
        baseRad: RADIUS + 0.32 + Math.random() * 0.7,
        baseY: local.y + (Math.random() - 0.5) * 0.55,
        angSpeed: (Math.random() - 0.5) * 0.5,
        f1: 0.3 + Math.random() * 0.5, p1: Math.random() * TWO_PI,
        f2: 0.3 + Math.random() * 0.5, p2: Math.random() * TWO_PI,
        f3: 0.3 + Math.random() * 0.5, p3: Math.random() * TWO_PI,
        scale: 0.6 + Math.random() * 0.7,
        local,
      });
    }
    return arr;
  }, []);

  const lineGeo = useMemo(() => {
    const g = new BufferGeometry();
    g.setAttribute("position", new Float32BufferAttribute(new Float32Array(DOT_COUNT * 6), 3));
    const colors = new Float32Array(DOT_COUNT * 6);
    const white = new Color(WHITE);
    const gold = new Color(GOLD);
    for (let i = 0; i < DOT_COUNT; i++) {
      const c = i % 2 === 0 ? gold : white;
      for (let v = 0; v < 2; v++) {
        colors[i * 6 + v * 3] = c.r;
        colors[i * 6 + v * 3 + 1] = c.g;
        colors[i * 6 + v * 3 + 2] = c.b;
      }
    }
    g.setAttribute("color", new Float32BufferAttribute(colors, 3));
    return g;
  }, []);

  // --- Refs ----------------------------------------------------------------
  const helixGroup = useRef<Group>(null);
  const ringA = useRef<Group>(null);
  const ringB = useRef<Group>(null);
  const dotsMesh = useRef<InstancedMesh>(null);
  const lineRef = useRef<LineSegments>(null);
  const keyLight = useRef<DirectionalLight>(null);
  const rimLight = useRef<DirectionalLight>(null);

  const dummy = useMemo(() => new Object3D(), []);
  const params = useRef({ ...STATE_PARAMS.idle });
  const driftT = useRef(0);

  // Assign per-dot instance colours once (white/gold alternating).
  useEffect(() => {
    const mesh = dotsMesh.current;
    if (!mesh) return;
    const white = new Color(WHITE);
    const gold = new Color(GOLD_HI);
    for (let i = 0; i < DOT_COUNT; i++) {
      mesh.setColorAt(i, i % 2 === 0 ? gold : white);
    }
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, []);

  useFrame((state, delta) => {
    const t = state.clock.elapsedTime;
    const target = STATE_PARAMS[voiceState];
    const k = Math.min(1, delta * 2.2);
    const p = params.current;
    const pulse = voiceState === "speaking" ? audioLevel : 0;

    p.spin += (target.spin + pulse * 0.25 - p.spin) * k;
    p.drift += (target.drift + pulse * 0.4 - p.drift) * k;
    p.bright += (target.bright + pulse * 0.15 - p.bright) * k;

    // Slow cinematic spin of the helix around Y.
    let spinAngle = 0;
    if (helixGroup.current) {
      helixGroup.current.rotation.y += delta * p.spin;
      spinAngle = helixGroup.current.rotation.y;
    }

    // Subtle light response (no glow — just dimensional brightness).
    if (keyLight.current) keyLight.current.intensity = 1.15 * p.bright;
    if (rimLight.current) rimLight.current.intensity = 0.5 * p.bright;

    // Counter-rotating aqua gyroscope rings (own spin, calm, reacts subtly).
    const ringSpin = 0.22 + p.spin * 0.35;
    if (ringA.current) ringA.current.rotation.y += delta * ringSpin;
    if (ringB.current) ringB.current.rotation.y -= delta * ringSpin * 0.85;

    // Advance the shared drift clock.
    driftT.current += delta * p.drift;
    const dt = driftT.current;

    const cosS = Math.cos(spinAngle);
    const sinS = Math.sin(spinAngle);

    const mesh = dotsMesh.current;
    const linePos = lineRef.current
      ? (lineRef.current.geometry.getAttribute("position").array as Float32Array)
      : null;

    for (let i = 0; i < DOT_COUNT; i++) {
      const d = dots[i];
      const ang = d.baseAngle + d.angSpeed * dt + Math.sin(t * d.f1 + d.p1) * 0.16;
      const rad = d.baseRad + Math.sin(t * d.f2 + d.p2) * 0.12;
      const yy = d.baseY + Math.sin(t * d.f3 + d.p3) * 0.18;
      const x = rad * Math.cos(ang);
      const z = rad * Math.sin(ang);

      if (mesh) {
        dummy.position.set(x, yy, z);
        dummy.scale.setScalar(d.scale * 0.026);
        dummy.updateMatrix();
        mesh.setMatrixAt(i, dummy.matrix);
      }

      if (linePos) {
        // Dot end.
        linePos[i * 6] = x;
        linePos[i * 6 + 1] = yy;
        linePos[i * 6 + 2] = z;
        // Helix end — rotate the assigned local point by the helix spin.
        const lx = d.local.x;
        const lz = d.local.z;
        linePos[i * 6 + 3] = lx * cosS + lz * sinS;
        linePos[i * 6 + 4] = d.local.y;
        linePos[i * 6 + 5] = -lx * sinS + lz * cosS;
      }
    }

    if (mesh) mesh.instanceMatrix.needsUpdate = true;
    if (lineRef.current && linePos) {
      lineRef.current.geometry.getAttribute("position").needsUpdate = true;
    }
  });

  return (
    // Slight cinematic tilt of the whole composition for depth.
    <group rotation={[0.18, 0, 0.12]}>
      <ambientLight intensity={0.55} />
      <directionalLight ref={keyLight} position={[2.5, 3, 4]} intensity={1.15} color="#ffffff" />
      <directionalLight ref={rimLight} position={[-3, -1.5, -2.5]} intensity={0.5} color={GOLD} />

      {/* Spinning double helix. */}
      <group ref={helixGroup}>
        <mesh geometry={strandA}>
          <meshStandardMaterial color={WHITE} roughness={0.32} metalness={0.15} />
        </mesh>
        <mesh geometry={strandB}>
          <meshStandardMaterial color={GOLD} roughness={0.28} metalness={0.45} />
        </mesh>

        {rungs.map((r, i) => (
          <mesh key={i} position={r.position} quaternion={r.quaternion}>
            <cylinderGeometry args={[0.016, 0.016, r.length, 8]} />
            <meshStandardMaterial
              color={r.gold ? GOLD : WHITE}
              roughness={0.4}
              metalness={r.gold ? 0.4 : 0.15}
            />
          </mesh>
        ))}
      </group>

      {/* Two counter-rotating aqua gyroscope rings encircling the helix. */}
      <group ref={ringA}>
        <mesh rotation={[0.55, 0, 0]}>
          <torusGeometry args={[1.15, 0.012, 12, 96]} />
          <meshStandardMaterial color={AQUA} roughness={0.3} metalness={0.4} />
        </mesh>
      </group>
      <group ref={ringB}>
        <mesh rotation={[-0.5, 0, 0.7]}>
          <torusGeometry args={[1.3, 0.011, 12, 96]} />
          <meshStandardMaterial color={AQUA} roughness={0.3} metalness={0.4} />
        </mesh>
      </group>

      {/* Free-flowing dots. */}
      <instancedMesh ref={dotsMesh} args={[undefined, undefined, DOT_COUNT]}>
        <sphereGeometry args={[1, 12, 12]} />
        <meshStandardMaterial roughness={0.4} metalness={0.1} />
      </instancedMesh>

      {/* Thin faint connector lines (dot -> helix point). */}
      <lineSegments ref={lineRef} geometry={lineGeo}>
        <lineBasicMaterial vertexColors transparent opacity={0.22} depthWrite={false} />
      </lineSegments>
    </group>
  );
}

export default HelixOrb;
