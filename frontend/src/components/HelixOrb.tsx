/**
 * HelixOrb — Helix's identity symbol. PURE SYMBOLISM, never a data view.
 *
 * "Fractured Halo" — a premium cinematic glass artefact:
 *
 *   1. HALO — a horizontal ring seen in 3/4 perspective (the group is tilted
 *      ~58° toward the camera so it reads as an ellipse with a near and far
 *      edge). It is FRACTURED into 6 chunky curved arc segments with gaps
 *      between them. Built by merging 6 partial-torus geometries into ONE
 *      mesh so a single (GPU-heavy) MeshTransmissionMaterial pass covers them
 *      all. Clear gold-tinted glass with a faint gold emissive sheen.
 *
 *   2. FILAMENTS — thin bright gold arcs threaded along the segment centrelines
 *      (one merged emissive mesh) plus a drifting gold Sparkles field, so light
 *      appears to run through and around the halo.
 *
 *   3. ATOMIC CORE — a white-hot nucleus floating at the centre, wrapped by 3
 *      thin tilted elliptical orbital rings (atom symbol) with a few small
 *      particles orbiting along them (angles advanced in useFrame).
 *
 *   4. BLOOM — an EffectComposer + Bloom pass (from @react-three/postprocessing)
 *      makes the gold emissives glow premium and cinematic. Tuned, not blown out.
 *
 * Voice reactivity is preserved via the unchanged `HelixOrb({ voiceState,
 * audioLevel })` signature; per-state knobs are lerped toward each frame and
 * stay deliberately calm/cinematic:
 *   idle      — slow halo rotation + gentle core.
 *   listening — slightly brighter.
 *   thinking  — faster rotation + brighter.
 *   speaking  — audioLevel drives core brightness + a subtle pulse + rotation.
 *
 * Palette: warm GOLD #ffc247 + white-hot #ffe9a8 / white only. No aqua/cyan,
 * no data fetching. One new dependency: @react-three/postprocessing.
 */

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { MeshTransmissionMaterial, Sparkles } from "@react-three/drei";
import { EffectComposer, Bloom } from "@react-three/postprocessing";
import {
  BufferGeometry,
  Euler,
  Group,
  Matrix4,
  Mesh,
  MeshStandardMaterial,
  TorusGeometry,
  Vector3,
} from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import type { VoiceState } from "../lib/types";

const GOLD = "#ffc247";
const GOLD_HI = "#ffe9a8";
const WHITE = "#fffdf5";
const TWO_PI = Math.PI * 2;

// --- Halo constants ---------------------------------------------------------
const SEGMENTS = 6; // fractured arc count
const HALO_R = 1.12; // ring radius
const HALO_TUBE = 0.1; // arc thickness
const GAP = 0.2; // radian gap between segments
const WALL_SCALE = 1.7; // stretch tube along ring normal → chunky "wall" look

// --- Orbital constants ------------------------------------------------------
const ORBIT_R = 0.34;
const PARTICLE_COUNT = 4;

/** Per-state behaviour knobs the animation lerps toward each frame. */
const STATE_PARAMS: Record<VoiceState, { rot: number; bright: number }> = {
  idle: { rot: 0.12, bright: 1.0 },
  listening: { rot: 0.16, bright: 1.2 },
  thinking: { rot: 0.4, bright: 1.28 },
  speaking: { rot: 0.18, bright: 1.1 },
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

export function HelixOrb({ voiceState, audioLevel }: OrbProps) {
  // --- Fractured-halo glass geometry (merged → one transmission pass) -------
  const haloGeo = useMemo(() => {
    const arc = TWO_PI / SEGMENTS - GAP;
    const parts: TorusGeometry[] = [];
    for (let i = 0; i < SEGMENTS; i++) {
      const g = new TorusGeometry(HALO_R, HALO_TUBE, 18, 40, arc);
      g.rotateZ(i * (TWO_PI / SEGMENTS) + GAP / 2);
      parts.push(g);
    }
    const merged = mergeGeometries(parts) as BufferGeometry;
    merged.scale(1, 1, WALL_SCALE); // chunky beveled wall along the normal
    parts.forEach((part) => part.dispose());
    return merged;
  }, []);

  // --- Filament geometry: thin bright arcs along the segment centrelines -----
  const filamentGeo = useMemo(() => {
    const arc = TWO_PI / SEGMENTS - GAP;
    const parts: TorusGeometry[] = [];
    for (let i = 0; i < SEGMENTS; i++) {
      const g = new TorusGeometry(HALO_R + 0.01, 0.014, 6, 36, arc);
      g.rotateZ(i * (TWO_PI / SEGMENTS) + GAP / 2);
      parts.push(g);
    }
    const merged = mergeGeometries(parts) as BufferGeometry;
    parts.forEach((part) => part.dispose());
    return merged;
  }, []);

  // --- Per-particle orbital descriptors (basis vectors + phase) -------------
  const particles = useMemo(() => {
    return Array.from({ length: PARTICLE_COUNT }, (_, i) => {
      const tilt = ORBIT_TILTS[i % ORBIT_TILTS.length];
      const m = new Matrix4().makeRotationFromEuler(tilt);
      const u = new Vector3(1, 0, 0).applyMatrix4(m); // in-plane axis 1
      const v = new Vector3(0, 1, 0).applyMatrix4(m); // in-plane axis 2
      return {
        u,
        v,
        phase: (i / PARTICLE_COUNT) * TWO_PI + i,
        speed: 0.9 + i * 0.25,
      };
    });
  }, []);

  // --- Refs -----------------------------------------------------------------
  const haloGroup = useRef<Group>(null);
  const coreGroup = useRef<Group>(null);
  const nucleus = useRef<Mesh>(null);
  const particleRefs = useRef<(Mesh | null)[]>([]);
  const params = useRef({ ...STATE_PARAMS.idle });

  useFrame((state, delta) => {
    const t = state.clock.elapsedTime;
    const target = STATE_PARAMS[voiceState];
    const k = Math.min(1, delta * 2.2);
    const p = params.current;
    const pulse = voiceState === "speaking" ? audioLevel : 0;

    p.rot += (target.rot + pulse * 0.25 - p.rot) * k;
    p.bright += (target.bright + pulse * 0.4 - p.bright) * k;

    // Slow cinematic rotation of the halo + gentle counter-spin of the core.
    if (haloGroup.current) haloGroup.current.rotation.z += delta * p.rot;
    if (coreGroup.current) coreGroup.current.rotation.y -= delta * (p.rot * 0.6 + 0.05);

    // Nucleus breathes / responds to voice.
    if (nucleus.current) {
      const mat = nucleus.current.material as MeshStandardMaterial;
      mat.emissiveIntensity = 2.2 * p.bright + pulse * 2.0 + 0.25 * Math.sin(t * 1.6);
      const s = 1 + 0.06 * Math.sin(t * 1.6) + pulse * 0.4;
      nucleus.current.scale.setScalar(s);
    }

    // Particles orbit along their tilted elliptical rings.
    for (let i = 0; i < particles.length; i++) {
      const mesh = particleRefs.current[i];
      if (!mesh) continue;
      const d = particles[i];
      const a = d.phase + t * d.speed * (1 + pulse * 0.6);
      const cos = Math.cos(a) * ORBIT_R;
      const sin = Math.sin(a) * ORBIT_R;
      mesh.position.set(
        d.u.x * cos + d.v.x * sin,
        d.u.y * cos + d.v.y * sin,
        d.u.z * cos + d.v.z * sin,
      );
    }
  });

  return (
    <>
      {/* Lighting — gives the glass dimensional shading + specular sparkle. */}
      <ambientLight intensity={0.4} />
      <directionalLight position={[3, 4, 5]} intensity={1.6} color={WHITE} />
      <directionalLight position={[-4, -2, -3]} intensity={0.7} color={GOLD} />
      <pointLight position={[0, 0, 0]} intensity={2.2} distance={4} color={GOLD_HI} />

      {/* Whole composition tilted into 3/4 perspective. */}
      <group rotation={[1.02, 0, 0.12]} scale={1.18}>
        {/* Fractured glass halo + filaments (rotate together). */}
        <group ref={haloGroup}>
          <mesh geometry={haloGeo}>
            <MeshTransmissionMaterial
              transmission={1}
              thickness={0.55}
              roughness={0.12}
              ior={1.45}
              chromaticAberration={0.06}
              anisotropy={0.1}
              distortion={0.1}
              distortionScale={0.2}
              temporalDistortion={0.1}
              resolution={256}
              samples={4}
              color={GOLD}
              attenuationColor={GOLD}
              attenuationDistance={1.4}
              emissive={GOLD}
              emissiveIntensity={0.35}
              toneMapped={false}
            />
          </mesh>

          {/* Bright gold filament threads along the segments. */}
          <mesh geometry={filamentGeo}>
            <meshStandardMaterial
              color={GOLD_HI}
              emissive={GOLD_HI}
              emissiveIntensity={2.4}
              toneMapped={false}
            />
          </mesh>

          {/* Drifting gold sparkle field weaving around the halo. */}
          <Sparkles
            count={36}
            scale={[2.6, 2.6, 0.8]}
            size={2.4}
            speed={0.3}
            noise={1.2}
            color={GOLD_HI}
          />
        </group>

        {/* Atomic core — nucleus + tilted orbital rings + orbiting particles. */}
        <group ref={coreGroup}>
          <mesh ref={nucleus}>
            <sphereGeometry args={[0.07, 24, 24]} />
            <meshStandardMaterial color={WHITE} emissive={GOLD_HI} emissiveIntensity={2.4} toneMapped={false} />
          </mesh>

          {ORBIT_TILTS.map((e, i) => (
            <mesh key={i} rotation={e}>
              <torusGeometry args={[ORBIT_R, 0.006, 8, 64]} />
              <meshStandardMaterial
                color={GOLD}
                emissive={GOLD}
                emissiveIntensity={1.6}
                toneMapped={false}
              />
            </mesh>
          ))}

          {particles.map((_, i) => (
            <mesh
              key={i}
              ref={(m) => {
                particleRefs.current[i] = m;
              }}
            >
              <sphereGeometry args={[0.022, 12, 12]} />
              <meshStandardMaterial color={GOLD_HI} emissive={GOLD_HI} emissiveIntensity={2.6} toneMapped={false} />
            </mesh>
          ))}
        </group>
      </group>

      {/* Cinematic bloom — makes the gold emissives glow without blowing out. */}
      <EffectComposer>
        <Bloom intensity={0.9} luminanceThreshold={0.2} luminanceSmoothing={0.9} radius={0.7} mipmapBlur />
      </EffectComposer>
    </>
  );
}

export default HelixOrb;
