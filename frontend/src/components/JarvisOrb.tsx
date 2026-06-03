/**
 * JarvisOrb — an ethereal "sand" particle orb rendered with React Three Fiber.
 *
 * 2500 additively-blended points sit on/around a sphere. Per-particle motion is
 * a cheap time-based sinusoidal noise drift (no external noise lib). Voice state
 * (from the Zustand store) drives colour, swirl speed, orbit tightness and — in
 * the speaking state — an amplitude-driven outward "explosion" pulse fed by the
 * live `audioLevel` (0..1, broadcast by the backend every 50ms during TTS).
 *
 * All transitions are lerped inside `useFrame` so colour/behaviour morph
 * smoothly between states rather than snapping.
 */

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import {
  AdditiveBlending,
  Color,
  type Points as ThreePoints,
  type PointsMaterial,
} from "three";
import type { VoiceState } from "../lib/types";

const PARTICLE_COUNT = 2500;
const BASE_RADIUS = 1.2;

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

export function JarvisOrb({ voiceState, audioLevel }: OrbProps) {
  const pointsRef = useRef<ThreePoints>(null);

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
    const mat = pts.material as PointsMaterial;
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

    const arr = (pts.geometry.attributes.position as { array: Float32Array; needsUpdate: boolean });
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
  });

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

export default JarvisOrb;
