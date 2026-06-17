/**
 * HelixOrb — Helix's identity symbol. PURE SYMBOLISM, never a data view.
 *
 * "Ethereal Halo" — a calm, white, glowing artefact:
 *
 *   1. TWO CROSSED HALOS — two fractured halos (6 chunky arc segments with
 *      gaps), each rendered as a WHITE GLOWING OUTLINE only (EdgesGeometry →
 *      LineSegments, emissive white). Halo A tumbles on its X axis, Halo B
 *      spins on its Y axis, so they cross like a slow gyroscope. No solid
 *      glass, no gold.
 *
 *   2. WHITE CORE — a soft white-glowing nucleus at the centre, wrapped by 3
 *      thin tilted white orbital-ring outlines (atom motif). Minimal, ethereal.
 *
 *   3. ETHEREAL DOTS — ~40 small soft-white dots drifting VERY slowly (tiny
 *      velocities + gentle noise), low opacity, soft glow. One InstancedMesh,
 *      matrices updated via useFrame (no per-dot React objects).
 *
 *   4. BLOOM — EffectComposer + Bloom (@react-three/postprocessing) makes the
 *      white outlines, dots and core glow ethereally.
 *
 * Voice reactivity is preserved via the unchanged `HelixOrb({ voiceState,
 * audioLevel })` signature; per-state knobs are lerped toward each frame and
 * stay deliberately calm/ethereal:
 *   idle      — slow halo rotation + gentle core.
 *   listening — slightly brighter.
 *   thinking  — a touch faster rotation + brighter.
 *   speaking  — audioLevel adds subtle core brightness + a little rotation.
 *
 * Palette: WHITE + soft glow only. No gold/aqua/cyan. No data fetching.
 */

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { EffectComposer, Bloom } from "@react-three/postprocessing";
import {
  BufferGeometry,
  EdgesGeometry,
  Euler,
  Group,
  InstancedMesh,
  LineSegments,
  Mesh,
  MeshStandardMaterial,
  Object3D,
  TorusGeometry,
} from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import type { VoiceState } from "../lib/types";

const WHITE = "#ffffff";
const SOFT_WHITE = "#f3f6ff";
const TWO_PI = Math.PI * 2;

// --- Halo constants ---------------------------------------------------------
const SEGMENTS = 6; // fractured arc count
const HALO_R = 1.12; // ring radius
const HALO_TUBE = 0.1; // arc thickness
const GAP = 0.2; // radian gap between segments
const WALL_SCALE = 1.7; // stretch tube along ring normal → chunky "wall" look

// --- Core / dots ------------------------------------------------------------
const ORBIT_R = 0.34;
const DOT_COUNT = 40;

/** Per-state behaviour knobs the animation lerps toward each frame. */
const STATE_PARAMS: Record<VoiceState, { rot: number; bright: number }> = {
  idle: { rot: 1.0, bright: 1.0 },
  listening: { rot: 1.1, bright: 1.18 },
  thinking: { rot: 1.5, bright: 1.25 },
  speaking: { rot: 1.15, bright: 1.12 },
};

interface OrbProps {
  voiceState: VoiceState;
  /** 0..1 live audio amplitude driving the speaking-state pulse. */
  audioLevel: number;
}

/** Three differently-tilted orbital-ring orientations for the atom core. */
const ORBIT_TILTS: Euler[] = [
  new Euler(0, 0, 0),
  new Euler(1.15, 0.5, 0),
  new Euler(-0.6, -0.9, 0.7),
];

/** Static per-dot drift descriptor (very slow, ethereal). */
interface DotData {
  bx: number; by: number; bz: number; // base position
  ax: number; ay: number; az: number; // drift amplitudes
  fx: number; fy: number; fz: number; // drift frequencies (very low)
  px: number; py: number; pz: number; // phases
  scale: number;
}

export function HelixOrb({ voiceState, audioLevel }: OrbProps) {
  // --- White outline geometry for one fractured halo ------------------------
  // Faceted arcs (low radialSegments) so EdgesGeometry yields clean longitudinal
  // edges; a high threshold drops the gentle along-arc curvature steps.
  const haloEdges = useMemo(() => {
    const arc = TWO_PI / SEGMENTS - GAP;
    const parts: TorusGeometry[] = [];
    for (let i = 0; i < SEGMENTS; i++) {
      const g = new TorusGeometry(HALO_R, HALO_TUBE, 4, 26, arc);
      g.rotateZ(i * (TWO_PI / SEGMENTS) + GAP / 2);
      parts.push(g);
    }
    const merged = mergeGeometries(parts) as BufferGeometry;
    merged.scale(1, 1, WALL_SCALE);
    const edges = new EdgesGeometry(merged, 18);
    merged.dispose();
    parts.forEach((part) => part.dispose());
    return edges;
  }, []);

  // --- Ethereal dot field (slow drift) --------------------------------------
  const dots = useMemo<DotData[]>(() => {
    return Array.from({ length: DOT_COUNT }, () => {
      // Even-ish spherical shell distribution.
      const u = Math.random() * 2 - 1;
      const theta = Math.random() * TWO_PI;
      const r = 1.0 + Math.random() * 0.9;
      const s = Math.sqrt(1 - u * u);
      return {
        bx: r * s * Math.cos(theta),
        by: r * u,
        bz: r * s * Math.sin(theta),
        ax: 0.05 + Math.random() * 0.06,
        ay: 0.05 + Math.random() * 0.06,
        az: 0.05 + Math.random() * 0.06,
        fx: 0.04 + Math.random() * 0.08, // very low frequency → almost still
        fy: 0.04 + Math.random() * 0.08,
        fz: 0.04 + Math.random() * 0.08,
        px: Math.random() * TWO_PI,
        py: Math.random() * TWO_PI,
        pz: Math.random() * TWO_PI,
        scale: 0.6 + Math.random() * 0.8,
      };
    });
  }, []);

  // --- Refs -----------------------------------------------------------------
  const haloA = useRef<LineSegments>(null);
  const haloB = useRef<LineSegments>(null);
  const coreGroup = useRef<Group>(null);
  const nucleus = useRef<Mesh>(null);
  const dotsMesh = useRef<InstancedMesh>(null);
  const params = useRef({ ...STATE_PARAMS.idle });
  const dummy = useMemo(() => new Object3D(), []);

  useFrame((state, delta) => {
    const t = state.clock.elapsedTime;
    const target = STATE_PARAMS[voiceState];
    const k = Math.min(1, delta * 2.0);
    const p = params.current;
    const pulse = voiceState === "speaking" ? audioLevel : 0;

    p.rot += (target.rot + pulse * 0.3 - p.rot) * k;
    p.bright += (target.bright + pulse * 0.4 - p.bright) * k;

    // Two crossed halos on different axes — slow, cinematic.
    if (haloA.current) haloA.current.rotation.x += delta * 0.16 * p.rot;
    if (haloB.current) haloB.current.rotation.y += delta * 0.13 * p.rot;

    // Gentle core drift + breathing nucleus.
    if (coreGroup.current) coreGroup.current.rotation.y += delta * 0.08 * p.rot;
    if (nucleus.current) {
      const mat = nucleus.current.material as MeshStandardMaterial;
      mat.emissiveIntensity = 2.0 * p.bright + pulse * 1.8 + 0.2 * Math.sin(t * 1.4);
      const s = 1 + 0.05 * Math.sin(t * 1.4) + pulse * 0.35;
      nucleus.current.scale.setScalar(s);
    }

    // Ethereal dots — barely-moving slow drift.
    const mesh = dotsMesh.current;
    if (mesh) {
      for (let i = 0; i < dots.length; i++) {
        const d = dots[i];
        dummy.position.set(
          d.bx + Math.sin(t * d.fx + d.px) * d.ax,
          d.by + Math.sin(t * d.fy + d.py) * d.ay,
          d.bz + Math.sin(t * d.fz + d.pz) * d.az,
        );
        dummy.scale.setScalar(d.scale * 0.018);
        dummy.updateMatrix();
        mesh.setMatrixAt(i, dummy.matrix);
      }
      mesh.instanceMatrix.needsUpdate = true;
    }
  });

  return (
    <>
      {/* Soft white lighting (outlines/dots/core are emissive; this is gentle fill). */}
      <ambientLight intensity={0.5} />
      <directionalLight position={[2, 3, 4]} intensity={0.8} color={WHITE} />

      {/* Two crossed white-outline halos. */}
      <lineSegments ref={haloA} geometry={haloEdges}>
        <lineBasicMaterial color={WHITE} transparent opacity={0.9} toneMapped={false} />
      </lineSegments>
      <lineSegments ref={haloB} geometry={haloEdges} rotation={[0, 0, Math.PI / 2]}>
        <lineBasicMaterial color={WHITE} transparent opacity={0.9} toneMapped={false} />
      </lineSegments>

      {/* Ethereal slow-drifting white dots. */}
      <instancedMesh ref={dotsMesh} args={[undefined, undefined, DOT_COUNT]}>
        <sphereGeometry args={[1, 10, 10]} />
        <meshStandardMaterial
          color={SOFT_WHITE}
          emissive={WHITE}
          emissiveIntensity={1.1}
          transparent
          opacity={0.65}
          toneMapped={false}
        />
      </instancedMesh>

      {/* White ethereal core — nucleus + thin white orbital-ring outlines. */}
      <group ref={coreGroup}>
        <mesh ref={nucleus}>
          <sphereGeometry args={[0.07, 24, 24]} />
          <meshStandardMaterial color={WHITE} emissive={WHITE} emissiveIntensity={2.0} toneMapped={false} />
        </mesh>

        {ORBIT_TILTS.map((e, i) => (
          <mesh key={i} rotation={e}>
            <torusGeometry args={[ORBIT_R, 0.005, 8, 64]} />
            <meshStandardMaterial
              color={SOFT_WHITE}
              emissive={WHITE}
              emissiveIntensity={1.4}
              toneMapped={false}
            />
          </mesh>
        ))}
      </group>

      {/* Cinematic bloom — makes the white outlines, dots and core glow. */}
      <EffectComposer>
        <Bloom intensity={0.9} luminanceThreshold={0.2} luminanceSmoothing={0.9} radius={0.7} mipmapBlur />
      </EffectComposer>
    </>
  );
}

export default HelixOrb;
