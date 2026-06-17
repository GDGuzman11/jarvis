/**
 * HelixOrb — Helix's identity symbol. PURE SYMBOLISM, never a data view.
 *
 * "Ethereal Halo" — a calm, glowing artefact that floats transparently on the
 * desktop (no post-processing, so the Tauri window stays truly transparent —
 * the glow is built from additive sprites + emissive materials instead of a
 * full-screen bloom pass, which was forcing an opaque backing square):
 *
 *   1. TWO CROSSED WHITE HALOS — two fractured halos (6 chunky arc segments
 *      with gaps), each a WHITE GLOWING OUTLINE (EdgesGeometry → LineSegments,
 *      emissive white). Halo A tumbles on its X axis, Halo B spins on its Y
 *      axis, crossing like a slow gyroscope.
 *
 *   2. GOLD CORE — a gold-glowing nucleus + an additive gold glow sprite at the
 *      centre, wrapped by 3 thin tilted GOLD orbital-ring outlines (atom motif).
 *
 *   3. ETHEREAL DOTS — ~40 soft-white additive glow points drifting gently but
 *      visibly (one Points object; positions updated via a typed array).
 *
 *   Glow is alpha-safe: additive sprites/points add light over the transparent
 *   framebuffer without writing an opaque background.
 *
 * Voice reactivity (unchanged signature) is lerped each frame, calm/ethereal:
 *   idle — slow rotation + gentle core; listening — slightly brighter;
 *   thinking — a touch faster + brighter; speaking — audioLevel adds subtle
 *   core brightness + a little rotation.
 *
 * Palette: WHITE outer halos + GOLD inner rings/core. No aqua/cyan, no data.
 */

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import {
  AdditiveBlending,
  BufferGeometry,
  CanvasTexture,
  Color,
  EdgesGeometry,
  Euler,
  Float32BufferAttribute,
  Group,
  LineSegments,
  Mesh,
  MeshStandardMaterial,
  Points,
  PointsMaterial,
  Sprite,
  SpriteMaterial,
  TorusGeometry,
} from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import type { VoiceState } from "../lib/types";

const WHITE = "#ffffff";
const SOFT_WHITE = "#f3f6ff";
const GOLD = "#ffc247";
const GOLD_HI = "#ffe9a8";
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

/** Static per-dot drift descriptor — clearly moving, but smooth/dreamy. */
interface DotData {
  bx: number; by: number; bz: number; // base position
  ax: number; ay: number; az: number; // drift amplitudes
  fx: number; fy: number; fz: number; // drift frequencies
  px: number; py: number; pz: number; // phases
}

/** Soft radial-gradient sprite texture (white → transparent) for the glows. */
function makeGlowTexture(): CanvasTexture {
  const size = 64;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0, "rgba(255,255,255,1)");
  g.addColorStop(0.28, "rgba(255,255,255,0.5)");
  g.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  const tex = new CanvasTexture(canvas);
  tex.needsUpdate = true;
  return tex;
}

export function HelixOrb({ voiceState, audioLevel }: OrbProps) {
  const glowTex = useMemo(makeGlowTexture, []);

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

  // --- Ethereal dot field: data + a single additive-glow Points object ------
  const dots = useMemo<DotData[]>(() => {
    return Array.from({ length: DOT_COUNT }, () => {
      const u = Math.random() * 2 - 1;
      const theta = Math.random() * TWO_PI;
      const r = 1.0 + Math.random() * 0.9;
      const s = Math.sqrt(1 - u * u);
      return {
        bx: r * s * Math.cos(theta),
        by: r * u,
        bz: r * s * Math.sin(theta),
        // ~3-4× the previous motion so they clearly drift (still smooth).
        ax: 0.18 + Math.random() * 0.2,
        ay: 0.18 + Math.random() * 0.2,
        az: 0.18 + Math.random() * 0.2,
        fx: 0.35 + Math.random() * 0.5,
        fy: 0.35 + Math.random() * 0.5,
        fz: 0.35 + Math.random() * 0.5,
        px: Math.random() * TWO_PI,
        py: Math.random() * TWO_PI,
        pz: Math.random() * TWO_PI,
      };
    });
  }, []);

  const dotPoints = useMemo(() => {
    const geo = new BufferGeometry();
    geo.setAttribute("position", new Float32BufferAttribute(new Float32Array(DOT_COUNT * 3), 3));
    const mat = new PointsMaterial({
      map: glowTex,
      color: new Color(SOFT_WHITE),
      size: 0.22,
      sizeAttenuation: true,
      transparent: true,
      opacity: 0.8,
      blending: AdditiveBlending,
      depthWrite: false,
      toneMapped: false,
    });
    return new Points(geo, mat);
  }, [glowTex]);

  // --- Additive gold glow sprite behind the nucleus -------------------------
  const coreGlow = useMemo(() => {
    const mat = new SpriteMaterial({
      map: glowTex,
      color: new Color(GOLD),
      transparent: true,
      opacity: 0.9,
      blending: AdditiveBlending,
      depthWrite: false,
      toneMapped: false,
    });
    const sprite = new Sprite(mat);
    sprite.scale.setScalar(0.95);
    return sprite;
  }, [glowTex]);

  // --- Refs -----------------------------------------------------------------
  const haloA = useRef<LineSegments>(null);
  const haloB = useRef<LineSegments>(null);
  const coreGroup = useRef<Group>(null);
  const nucleus = useRef<Mesh>(null);
  const params = useRef({ ...STATE_PARAMS.idle });

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

    // Gentle core drift + breathing gold nucleus/glow.
    if (coreGroup.current) coreGroup.current.rotation.y += delta * 0.08 * p.rot;
    if (nucleus.current) {
      const mat = nucleus.current.material as MeshStandardMaterial;
      mat.emissiveIntensity = 2.0 * p.bright + pulse * 1.8 + 0.2 * Math.sin(t * 1.4);
      const s = 1 + 0.05 * Math.sin(t * 1.4) + pulse * 0.35;
      nucleus.current.scale.setScalar(s);
    }
    const glowS = 0.95 * p.bright + pulse * 0.5 + 0.05 * Math.sin(t * 1.4);
    coreGlow.scale.setScalar(glowS);
    (coreGlow.material as SpriteMaterial).opacity = 0.7 * p.bright + pulse * 0.3;

    // Ethereal dots — clearly drifting, smooth.
    const pos = dotPoints.geometry.attributes.position.array as Float32Array;
    for (let i = 0; i < dots.length; i++) {
      const d = dots[i];
      pos[i * 3] = d.bx + Math.sin(t * d.fx + d.px) * d.ax;
      pos[i * 3 + 1] = d.by + Math.sin(t * d.fy + d.py) * d.ay;
      pos[i * 3 + 2] = d.bz + Math.sin(t * d.fz + d.pz) * d.az;
    }
    dotPoints.geometry.attributes.position.needsUpdate = true;
  });

  return (
    <>
      {/* Soft fill light (most elements are emissive; this is gentle shading). */}
      <ambientLight intensity={0.5} />
      <directionalLight position={[2, 3, 4]} intensity={0.6} color={WHITE} />

      {/* Two crossed white-outline halos. */}
      <lineSegments ref={haloA} geometry={haloEdges}>
        <lineBasicMaterial color={WHITE} transparent opacity={0.9} toneMapped={false} />
      </lineSegments>
      <lineSegments ref={haloB} geometry={haloEdges} rotation={[0, 0, Math.PI / 2]}>
        <lineBasicMaterial color={WHITE} transparent opacity={0.9} toneMapped={false} />
      </lineSegments>

      {/* Ethereal slow-drifting white glow points. */}
      <primitive object={dotPoints} />

      {/* Gold ethereal core — glow sprite + nucleus + thin gold orbital rings. */}
      <group ref={coreGroup}>
        <primitive object={coreGlow} />
        <mesh ref={nucleus}>
          <sphereGeometry args={[0.07, 24, 24]} />
          <meshStandardMaterial color={GOLD_HI} emissive={GOLD} emissiveIntensity={2.0} toneMapped={false} />
        </mesh>

        {ORBIT_TILTS.map((e, i) => (
          <mesh key={i} rotation={e}>
            <torusGeometry args={[ORBIT_R, 0.005, 8, 64]} />
            <meshStandardMaterial
              color={GOLD}
              emissive={GOLD}
              emissiveIntensity={1.5}
              toneMapped={false}
            />
          </mesh>
        ))}
      </group>
    </>
  );
}

export default HelixOrb;
