/**
 * MemoryCore — the gold/white pulsing nucleus at the origin that every neuron
 * tethers to (echoes the orb's Ethereal-Halo core). An emissive nucleus + an
 * additive glow sprite; bloom (added in MemoryBrain) makes it bleed light.
 */

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import {
  AdditiveBlending,
  CanvasTexture,
  Color,
  Mesh,
  MeshStandardMaterial,
  Sprite,
  SpriteMaterial,
} from "three";

function makeGlow(): CanvasTexture {
  const size = 64;
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const ctx = c.getContext("2d")!;
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0, "rgba(255,255,255,1)");
  g.addColorStop(0.3, "rgba(255,210,120,0.5)");
  g.addColorStop(1, "rgba(255,194,71,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  const tex = new CanvasTexture(c);
  tex.needsUpdate = true;
  return tex;
}

export default function MemoryCore() {
  const tex = useMemo(makeGlow, []);
  const nucleus = useRef<Mesh>(null);
  const glow = useMemo(() => {
    const s = new Sprite(
      new SpriteMaterial({
        map: tex,
        color: new Color(1, 0.78, 0.36),
        transparent: true,
        blending: AdditiveBlending,
        depthWrite: false,
        toneMapped: false,
      }),
    );
    s.scale.setScalar(1.6);
    // The core glow must not intercept the hover raycast — neurons near or
    // behind it would otherwise never register a hover.
    s.raycast = () => null;
    return s;
  }, [tex]);

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    if (nucleus.current) {
      const mat = nucleus.current.material as MeshStandardMaterial;
      mat.emissiveIntensity = 2.2 + 0.4 * Math.sin(t * 1.3);
      nucleus.current.scale.setScalar(1 + 0.06 * Math.sin(t * 1.3));
    }
    glow.scale.setScalar(1.5 + 0.18 * Math.sin(t * 1.3));
  });

  return (
    <group>
      <primitive object={glow} />
      <mesh ref={nucleus} raycast={() => null}>
        <sphereGeometry args={[0.16, 24, 24]} />
        <meshStandardMaterial color="#ffe9a8" emissive="#ffc247" emissiveIntensity={2.2} toneMapped={false} />
      </mesh>
    </group>
  );
}
