/**
 * HelixOrb — Helix's identity orb. PURE SYMBOLISM, never a data view.
 *
 * The look is an "arc-reactor tech core wrapped in a flowing neuron field":
 *
 *   1. ARC-REACTOR CORE — a white-hot core sphere with a soft additive energy
 *      halo, wrapped by two thin concentric rings (TorusGeometry) and a
 *      segmented aqua coil ring (a circle of small boxes evoking the Iron Man
 *      reactor coil). The rings spin slowly on different axes and the core
 *      pulses like an energy source.
 *
 *   2. NEURON FIELD — 280 glowing points on a spherical shell around the core,
 *      held in a single THREE.Points. They move IN UNISON: a shared smooth flow
 *      field + a shared orbital rotation push every point, with a soft radial
 *      spring back to the shell so the cloud orbits the core as one organism.
 *      Positions live in one typed array updated each frame (no React objects).
 *
 *   3. HOVER — pointer rays hit an invisible catcher sphere; the neurons within
 *      a world-space radius of the hit point brighten and grow (smooth falloff),
 *      easing back to rest when the pointer leaves.
 *
 * Voice reactivity is preserved via the unchanged `HelixOrb({ voiceState,
 * audioLevel })` signature; per-state "knobs" are lerped toward each frame:
 *   idle      — calm slow flow + soft pulse.
 *   listening — brighter + cool aqua shimmer.
 *   thinking  — faster flow + brighter core.
 *   speaking  — audioLevel drives core brightness + scale/energy pulse + flow.
 *
 * Palette: gold #ffc247 structure, white-hot #ffe9a8 core, aqua #3fe3d0 energy.
 * No cyan, no data fetching, no new dependencies. GLSL inlined.
 */

import { useMemo, useRef } from "react";
import { useFrame, type ThreeEvent } from "@react-three/fiber";
import {
  AdditiveBlending,
  BackSide,
  BufferGeometry,
  Float32BufferAttribute,
  Group,
  IcosahedronGeometry,
  Mesh,
  Points,
  ShaderMaterial,
  Vector3,
} from "three";
import type { VoiceState } from "../lib/types";

const NEURON_COUNT = 280;
const SHELL_MIN = 1.55;
const SHELL_MAX = 2.15;
const HOVER_RADIUS = 0.85; // world-space radius of the hover highlight
const FLOW_BASE = 0.18; // base flow-field velocity scale
const SPRING = 1.5; // pull strength back toward the shell radius

/** Per-state behaviour knobs the animation lerps toward each frame. */
const STATE_PARAMS: Record<
  VoiceState,
  {
    flow: number; // flow-field + turbulence speed
    orbit: number; // shared orbital angular velocity (rad/s)
    pBright: number; // neuron brightness multiplier
    cBright: number; // core brightness multiplier
    cool: number; // aqua shimmer mix (0..1) — listening only
    size: number; // base point size
  }
> = {
  idle: { flow: 0.35, orbit: 0.1, pBright: 0.85, cBright: 1.0, cool: 0.0, size: 16 },
  listening: { flow: 0.45, orbit: 0.12, pBright: 1.05, cBright: 1.1, cool: 0.6, size: 16 },
  thinking: { flow: 0.95, orbit: 0.26, pBright: 1.1, cBright: 1.4, cool: 0.0, size: 16 },
  speaking: { flow: 0.6, orbit: 0.15, pBright: 1.0, cBright: 1.1, cool: 0.1, size: 18 },
};

interface OrbProps {
  voiceState: VoiceState;
  /** 0..1 live audio amplitude driving the speaking-state pulse. */
  audioLevel: number;
}

// --- Neuron point shaders ---------------------------------------------------
const POINT_VERT = /* glsl */ `
attribute float aBright;
varying float vBright;
uniform float uSize;
uniform float uPixelRatio;
void main() {
  vBright = aBright;
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = uSize * (1.0 + aBright * 2.0) * uPixelRatio / max(-mv.z, 0.1);
}
`;

const POINT_FRAG = /* glsl */ `
precision highp float;
varying float vBright;
uniform float uBrightness;
uniform float uCool;
void main() {
  vec2 uv = gl_PointCoord - 0.5;
  float alpha = smoothstep(0.5, 0.0, length(uv)); // soft round glow
  vec3 gold = vec3(1.0, 0.760, 0.278); // #ffc247
  vec3 hot  = vec3(1.0, 0.914, 0.659); // #ffe9a8
  vec3 aqua = vec3(0.247, 0.890, 0.816); // #3fe3d0
  vec3 c = mix(gold, aqua, uCool * 0.7);
  c = mix(c, hot, clamp(vBright, 0.0, 1.0));
  float intensity = uBrightness * (0.6 + vBright * 1.4);
  gl_FragColor = vec4(c * intensity, alpha);
}
`;

// --- Core sphere shaders (white-hot center → gold rim) ----------------------
const CORE_VERT = /* glsl */ `
varying vec3 vN;
varying vec3 vV;
void main() {
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  vN = normalize(normalMatrix * normal);
  vV = normalize(-mv.xyz);
  gl_Position = projectionMatrix * mv;
}
`;

const CORE_FRAG = /* glsl */ `
precision highp float;
varying vec3 vN;
varying vec3 vV;
uniform float uBrightness;
void main() {
  float f = max(dot(vN, vV), 0.0);
  vec3 gold = vec3(1.0, 0.760, 0.278);
  vec3 hot  = vec3(1.0, 0.914, 0.659);
  vec3 c = mix(gold, hot, pow(f, 1.5));
  c += vec3(1.0) * pow(f, 4.0) * 0.6; // white-hot centre
  gl_FragColor = vec4(c * uBrightness, 1.0);
}
`;

// --- Additive energy halo (back-side fresnel) -------------------------------
const HALO_FRAG = /* glsl */ `
precision highp float;
varying vec3 vN;
varying vec3 vV;
uniform float uBrightness;
uniform float uCool;
void main() {
  float fres = pow(1.0 - max(dot(vN, vV), 0.0), 2.5);
  vec3 gold = vec3(1.0, 0.760, 0.278);
  vec3 aqua = vec3(0.247, 0.890, 0.816);
  vec3 c = mix(gold, aqua, 0.35 + uCool * 0.45);
  gl_FragColor = vec4(c * fres * uBrightness, fres);
}
`;

export function HelixOrb({ voiceState, audioLevel }: OrbProps) {
  // --- Build the neuron Points + core/halo meshes once (imperative so we can
  //     mutate the position buffer and drive uniforms directly each frame). ---
  const built = useMemo(() => {
    const positions = new Float32Array(NEURON_COUNT * 3);
    const homeR = new Float32Array(NEURON_COUNT);
    const bright = new Float32Array(NEURON_COUNT);

    for (let i = 0; i < NEURON_COUNT; i++) {
      const t = (i + 0.5) / NEURON_COUNT;
      const inc = Math.acos(1 - 2 * t); // even polar distribution
      const az = i * 2.399963; // golden angle
      const r = SHELL_MIN + Math.random() * (SHELL_MAX - SHELL_MIN);
      const s = Math.sin(inc);
      positions[i * 3] = r * s * Math.cos(az);
      positions[i * 3 + 1] = r * Math.cos(inc);
      positions[i * 3 + 2] = r * s * Math.sin(az);
      homeR[i] = r;
    }

    const geo = new BufferGeometry();
    geo.setAttribute("position", new Float32BufferAttribute(positions, 3));
    geo.setAttribute("aBright", new Float32BufferAttribute(bright, 1));

    const pixelRatio = Math.min(typeof window !== "undefined" ? window.devicePixelRatio : 1, 2);
    const pointMat = new ShaderMaterial({
      uniforms: {
        uSize: { value: STATE_PARAMS.idle.size },
        uPixelRatio: { value: pixelRatio },
        uBrightness: { value: STATE_PARAMS.idle.pBright },
        uCool: { value: 0 },
      },
      vertexShader: POINT_VERT,
      fragmentShader: POINT_FRAG,
      transparent: true,
      depthWrite: false,
      blending: AdditiveBlending,
    });
    const points = new Points(geo, pointMat);

    const coreMat = new ShaderMaterial({
      uniforms: { uBrightness: { value: STATE_PARAMS.idle.cBright } },
      vertexShader: CORE_VERT,
      fragmentShader: CORE_FRAG,
    });
    const core = new Mesh(new IcosahedronGeometry(0.3, 4), coreMat);

    const haloMat = new ShaderMaterial({
      uniforms: { uBrightness: { value: STATE_PARAMS.idle.cBright }, uCool: { value: 0 } },
      vertexShader: CORE_VERT,
      fragmentShader: HALO_FRAG,
      transparent: true,
      depthWrite: false,
      blending: AdditiveBlending,
      side: BackSide,
    });
    const halo = new Mesh(new IcosahedronGeometry(0.62, 3), haloMat);

    return { positions, homeR, bright, geo, points, pointMat, core, coreMat, halo, haloMat };
  }, []);

  // 14-segment coil ring positions (XY plane), built once.
  const coils = useMemo(
    () => Array.from({ length: 14 }, (_, i) => (i / 14) * Math.PI * 2),
    [],
  );

  // --- Refs ----------------------------------------------------------------
  const coreGroup = useRef<Group>(null);
  const ringA = useRef<Mesh>(null);
  const ringB = useRef<Mesh>(null);
  const coilRing = useRef<Group>(null);
  const params = useRef({ ...STATE_PARAMS.idle });
  const flowTime = useRef(0);
  const orbitAngle = useRef(0);
  const hover = useRef({ active: false, point: new Vector3() });

  const onHoverMove = (e: ThreeEvent<PointerEvent>) => {
    hover.current.active = true;
    hover.current.point.copy(e.point);
  };
  const onHoverOut = () => {
    hover.current.active = false;
  };

  useFrame((state, delta) => {
    const t = state.clock.elapsedTime;
    const target = STATE_PARAMS[voiceState];
    const k = Math.min(1, delta * 2.5);
    const p = params.current;
    p.flow += (target.flow - p.flow) * k;
    p.orbit += (target.orbit - p.orbit) * k;
    p.pBright += (target.pBright - p.pBright) * k;
    p.cBright += (target.cBright - p.cBright) * k;
    p.cool += (target.cool - p.cool) * k;
    p.size += (target.size - p.size) * k;

    const pulse = voiceState === "speaking" ? audioLevel : 0;

    // Advance the shared flow field + shared orbital rotation.
    flowTime.current += delta * (0.3 + p.flow + pulse);
    orbitAngle.current += delta * p.orbit;
    const ft = flowTime.current;
    const omega = p.orbit + pulse * 0.2; // shared angular velocity

    const pos = built.positions;
    const homeR = built.homeR;
    const br = built.bright;
    const hov = hover.current;
    const hx = hov.point.x;
    const hy = hov.point.y;
    const hz = hov.point.z;

    for (let i = 0; i < NEURON_COUNT; i++) {
      const ix = i * 3;
      let x = pos[ix];
      let y = pos[ix + 1];
      let z = pos[ix + 2];

      // Smooth, coherent flow field — neighbours share velocities (unison).
      const fx = Math.sin(y * 0.7 + ft) + Math.cos(z * 0.7 - ft * 0.7);
      const fy = Math.sin(z * 0.7 + ft * 1.1) + Math.cos(x * 0.7 - ft * 0.5);
      const fz = Math.sin(x * 0.7 + ft * 0.9) + Math.cos(y * 0.7 - ft * 0.8);
      const fs = FLOW_BASE * p.flow * delta;

      // Shared orbital velocity around the Y axis: omega × position.
      x += fx * fs + omega * z * delta;
      y += fy * fs;
      z += fz * fs - omega * x * delta;

      // Soft radial spring keeps the cloud cohesive on its shell.
      const len = Math.sqrt(x * x + y * y + z * z) || 1e-4;
      const newLen = len + (homeR[i] - len) * Math.min(1, SPRING * delta);
      const sc = newLen / len;
      x *= sc;
      y *= sc;
      z *= sc;

      pos[ix] = x;
      pos[ix + 1] = y;
      pos[ix + 2] = z;

      // Hover highlight — brighten neurons near the cursor's world hit point.
      let tBright = 0;
      if (hov.active) {
        const dx = x - hx;
        const dy = y - hy;
        const dz = z - hz;
        const d = Math.sqrt(dx * dx + dy * dy + dz * dz);
        tBright = Math.max(0, 1 - d / HOVER_RADIUS);
        tBright *= tBright; // sharper falloff
      }
      br[i] += (tBright - br[i]) * Math.min(1, delta * 6);
    }
    built.geo.attributes.position.needsUpdate = true;
    built.geo.attributes.aBright.needsUpdate = true;

    // Neuron uniforms.
    const pu = built.pointMat.uniforms;
    pu.uBrightness.value = p.pBright + pulse * 0.4;
    pu.uCool.value = p.cool;
    pu.uSize.value = p.size;

    // Core energy pulse + brightness.
    const energy = 0.5 + 0.5 * Math.sin(t * 1.8) + pulse;
    const coreBright = p.cBright * (0.85 + 0.15 * energy) + pulse * 0.8;
    built.coreMat.uniforms.uBrightness.value = coreBright;
    built.haloMat.uniforms.uBrightness.value = coreBright * 0.9;
    built.haloMat.uniforms.uCool.value = p.cool;

    // Core breathing / speaking scale pulse.
    if (coreGroup.current) {
      const s = 1 + 0.04 * Math.sin(t * 1.6) + pulse * 0.25;
      coreGroup.current.scale.setScalar(s);
      coreGroup.current.rotation.z += delta * 0.04;
    }
    // Rings spin on different axes / speeds.
    if (ringA.current) ringA.current.rotation.z += delta * 0.3;
    if (ringB.current) {
      ringB.current.rotation.x += delta * 0.45;
      ringB.current.rotation.z -= delta * 0.15;
    }
    if (coilRing.current) {
      coilRing.current.rotation.z -= delta * 0.5;
      coilRing.current.scale.setScalar(1 + 0.06 * energy);
    }
  });

  return (
    <group>
      <primitive object={built.points} />

      <group ref={coreGroup} rotation={[0.35, 0, 0]}>
        <primitive object={built.halo} />
        <primitive object={built.core} />

        {/* Concentric structural rings (gold) + aqua accent ring. */}
        <mesh ref={ringA}>
          <torusGeometry args={[0.58, 0.014, 12, 64]} />
          <meshBasicMaterial color="#ffc247" toneMapped={false} />
        </mesh>
        <mesh ref={ringB}>
          <torusGeometry args={[0.78, 0.01, 12, 64]} />
          <meshBasicMaterial color="#3fe3d0" toneMapped={false} />
        </mesh>

        {/* Segmented arc-reactor coil ring — aqua energy. */}
        <group ref={coilRing}>
          {coils.map((a, i) => (
            <mesh
              key={i}
              position={[Math.cos(a) * 0.46, Math.sin(a) * 0.46, 0]}
              rotation={[0, 0, a]}
            >
              <boxGeometry args={[0.05, 0.11, 0.025]} />
              <meshBasicMaterial color="#3fe3d0" toneMapped={false} />
            </mesh>
          ))}
        </group>
      </group>

      {/* Invisible catcher sphere — feeds pointer hits to the hover highlight. */}
      <mesh onPointerMove={onHoverMove} onPointerOut={onHoverOut}>
        <sphereGeometry args={[2.5, 16, 16]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
    </group>
  );
}

export default HelixOrb;
