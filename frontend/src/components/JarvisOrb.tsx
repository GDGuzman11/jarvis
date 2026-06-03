/**
 * JarvisOrb — the reactive HUD orb rendered with React Three Fiber.
 *
 * Colour encodes voice state (blue idle, gold thinking, cyan speaking/listening)
 * and the orb scale + distortion react to the live audio amplitude from the
 * store. All animation happens inside `useFrame` with lerped transitions so
 * colour and motion change smoothly rather than snapping.
 */

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Color, type Mesh, type MeshStandardMaterial } from "three";
import type { VoiceState } from "../lib/types";

const STATE_COLOR: Record<VoiceState, string> = {
  idle: "#00d4ff", // electric blue
  listening: "#00ffff", // cyan
  thinking: "#ffb800", // gold
  speaking: "#00ffff", // cyan-bright
};

interface OrbProps {
  voiceState: VoiceState;
  /** 0..1 live audio amplitude driving pulse intensity. */
  audioLevel: number;
}

export function JarvisOrb({ voiceState, audioLevel }: OrbProps) {
  const meshRef = useRef<Mesh>(null);
  const matRef = useRef<MeshStandardMaterial>(null);
  const target = useMemo(() => new Color(STATE_COLOR[voiceState]), [voiceState]);

  useFrame((state, delta) => {
    const t = state.clock.elapsedTime;
    const mesh = meshRef.current;
    const mat = matRef.current;
    if (!mesh || !mat) return;

    // Smoothly lerp the emissive colour toward the target voice-state colour.
    mat.emissive.lerp(target, Math.min(1, delta * 4));
    mat.color.lerp(target, Math.min(1, delta * 4));

    // Base breathing pulse + audio-reactive amplitude. Thinking/speaking states
    // breathe faster; the live audioLevel adds an extra reactive push.
    const speed = voiceState === "idle" ? 1.1 : 2.2;
    const breathe = 0.06 * Math.sin(t * speed);
    const reactive = audioLevel * 0.5;
    const scale = 1 + breathe + reactive;
    mesh.scale.setScalar(scale);

    // Glow intensity rises with activity and audio.
    mat.emissiveIntensity = 0.6 + reactive * 1.6 + (voiceState !== "idle" ? 0.4 : 0);

    // Slow rotation for life.
    mesh.rotation.y += delta * 0.25;
    mesh.rotation.x += delta * 0.08;
  });

  return (
    <group>
      <ambientLight intensity={0.4} />
      <pointLight position={[4, 4, 4]} intensity={1.2} color="#00d4ff" />
      <pointLight position={[-4, -2, -4]} intensity={0.6} color="#ffb800" />
      <mesh ref={meshRef}>
        <icosahedronGeometry args={[1.2, 6]} />
        <meshStandardMaterial
          ref={matRef}
          color={STATE_COLOR[voiceState]}
          emissive={STATE_COLOR[voiceState]}
          emissiveIntensity={0.8}
          roughness={0.25}
          metalness={0.6}
          wireframe
        />
      </mesh>
      {/* Inner solid core for depth. */}
      <mesh scale={0.7}>
        <sphereGeometry args={[1, 32, 32]} />
        <meshBasicMaterial color={STATE_COLOR[voiceState]} transparent opacity={0.12} />
      </mesh>
    </group>
  );
}

export default JarvisOrb;
