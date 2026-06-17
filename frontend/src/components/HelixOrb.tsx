/**
 * HelixOrb — the molten fiery core.
 *
 * Helix's identity orb. PURE SYMBOLISM, not a data view: a roiling ball of
 * champagne-gold fire. A solid core sphere is shaded by a custom ShaderMaterial
 * whose fragment shader runs animated FBM/simplex noise to paint a molten
 * surface — dark gold troughs rising through `#ffc247` and `#ffe9a8` to
 * white-hot crests. A larger additive-fresnel corona bleeds light at the rim.
 * The whole thing flickers like flame and breathes (slow scale pulse).
 *
 * Voice reactivity is preserved: the `HelixOrb({ voiceState, audioLevel })`
 * signature is unchanged, and per-state behaviour "knobs" are lerped toward
 * each frame (smooth transitions). State → fire:
 *   idle      — calm, slow flicker, mild heat.
 *   listening — brighter + cooler aqua shimmer.
 *   thinking  — hotter, faster turbulence, more displacement.
 *   speaking  — audioLevel drives flicker intensity + a scale pulse.
 *
 * No neuron points / connections / symbols / hologram shell remain — those
 * belonged to the old neural orb. Inline GLSL simplex noise (Ashima/Gustavson),
 * no new dependency.
 */

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import {
  AdditiveBlending,
  BackSide,
  IcosahedronGeometry,
  Mesh,
  ShaderMaterial,
} from "three";
import type { VoiceState } from "../lib/types";

// --- Core geometry ----------------------------------------------------------
const BASE_RADIUS = 1.2; // preserved orb size
const CORONA_SCALE = 1.32; // corona radius relative to the core

// --- Champagne-gold fire palette (also hard-coded in the GLSL below) --------
// dark gold trough → #ffc247 → #ffe9a8 → white-hot crest, with a cool aqua
// (#3fe3d0) shimmer mixed in during the listening state.

/** Per-state behaviour knobs the animation lerps toward. */
const STATE_PARAMS: Record<
  VoiceState,
  {
    scale: number; // base breathing scale
    brightness: number; // emissive multiplier
    turbulence: number; // noise flow speed + displacement
    hot: number; // how white-hot the crests get (0..1)
    cool: number; // aqua shimmer mix (0..1) — listening only
  }
> = {
  idle: { scale: 1.0, brightness: 0.85, turbulence: 0.5, hot: 0.4, cool: 0.0 },
  listening: { scale: 0.97, brightness: 1.05, turbulence: 0.75, hot: 0.5, cool: 0.45 },
  thinking: { scale: 1.05, brightness: 1.22, turbulence: 1.7, hot: 0.9, cool: 0.0 },
  speaking: { scale: 1.0, brightness: 1.0, turbulence: 1.1, hot: 0.6, cool: 0.1 },
};

interface OrbProps {
  voiceState: VoiceState;
  /** 0..1 live audio amplitude driving the speaking-state pulse. */
  audioLevel: number;
}

// --- Inline GLSL: Ashima/Gustavson 3D simplex noise + FBM -------------------
const NOISE_GLSL = /* glsl */ `
vec3 mod289(vec3 x){return x - floor(x * (1.0 / 289.0)) * 289.0;}
vec4 mod289(vec4 x){return x - floor(x * (1.0 / 289.0)) * 289.0;}
vec4 permute(vec4 x){return mod289(((x * 34.0) + 1.0) * x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159 - 0.85373472095314 * r;}
float snoise(vec3 v){
  const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);
  const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
  vec3 i  = floor(v + dot(v, C.yyy));
  vec3 x0 = v - i + dot(i, C.xxx);
  vec3 g = step(x0.yzx, x0.xyz);
  vec3 l = 1.0 - g;
  vec3 i1 = min(g.xyz, l.zxy);
  vec3 i2 = max(g.xyz, l.zxy);
  vec3 x1 = x0 - i1 + C.xxx;
  vec3 x2 = x0 - i2 + C.yyy;
  vec3 x3 = x0 - D.yyy;
  i = mod289(i);
  vec4 p = permute(permute(permute(
            i.z + vec4(0.0, i1.z, i2.z, 1.0))
          + i.y + vec4(0.0, i1.y, i2.y, 1.0))
          + i.x + vec4(0.0, i1.x, i2.x, 1.0));
  float n_ = 0.142857142857;
  vec3 ns = n_ * D.wyz - D.xzx;
  vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
  vec4 x_ = floor(j * ns.z);
  vec4 y_ = floor(j - 7.0 * x_);
  vec4 x = x_ * ns.x + ns.yyyy;
  vec4 y = y_ * ns.x + ns.yyyy;
  vec4 h = 1.0 - abs(x) - abs(y);
  vec4 b0 = vec4(x.xy, y.xy);
  vec4 b1 = vec4(x.zw, y.zw);
  vec4 s0 = floor(b0) * 2.0 + 1.0;
  vec4 s1 = floor(b1) * 2.0 + 1.0;
  vec4 sh = -step(h, vec4(0.0));
  vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
  vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
  vec3 p0 = vec3(a0.xy, h.x);
  vec3 p1 = vec3(a0.zw, h.y);
  vec3 p2 = vec3(a1.xy, h.z);
  vec3 p3 = vec3(a1.zw, h.w);
  vec4 norm = taylorInvSqrt(vec4(dot(p0, p0), dot(p1, p1), dot(p2, p2), dot(p3, p3)));
  p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
  vec4 m = max(0.6 - vec4(dot(x0, x0), dot(x1, x1), dot(x2, x2), dot(x3, x3)), 0.0);
  m = m * m;
  return 42.0 * dot(m * m, vec4(dot(p0, x0), dot(p1, x1), dot(p2, x2), dot(p3, x3)));
}
float fbm(vec3 p){
  float v = 0.0;
  float a = 0.5;
  for (int i = 0; i < 5; i++) {
    v += a * snoise(p);
    p *= 2.0;
    a *= 0.5;
  }
  return v;
}
`;

const CORE_VERT = /* glsl */ `
varying vec3 vObjPos;
varying vec3 vNormalV;
varying vec3 vViewDir;
uniform float uTime;
uniform float uNoiseScale;
uniform float uDisplace;
${NOISE_GLSL}
void main() {
  vObjPos = position;
  float disp = fbm(position * uNoiseScale + vec3(0.0, uTime * 0.3, 0.0)) * uDisplace;
  vec3 displaced = position + normal * disp;
  vec4 mvPosition = modelViewMatrix * vec4(displaced, 1.0);
  vNormalV = normalize(normalMatrix * normal);
  vViewDir = normalize(-mvPosition.xyz);
  gl_Position = projectionMatrix * mvPosition;
}
`;

const CORE_FRAG = /* glsl */ `
precision highp float;
varying vec3 vObjPos;
varying vec3 vNormalV;
varying vec3 vViewDir;
uniform float uTime;
uniform float uBrightness;
uniform float uHot;
uniform float uCool;
uniform float uFlicker;
uniform float uNoiseScale;
${NOISE_GLSL}
void main() {
  float n = fbm(vObjPos * uNoiseScale * 1.3 + vec3(uTime * 0.25, uTime * 0.15, -uTime * 0.2));
  n += 0.4 * fbm(vObjPos * uNoiseScale * 3.0 - vec3(uTime * 0.4));
  float heat = clamp(n * 0.55 + 0.5, 0.0, 1.0);

  vec3 cDark   = vec3(0.30, 0.15, 0.02); // deep gold trough
  vec3 cGold   = vec3(1.000, 0.760, 0.278); // #ffc247
  vec3 cBright = vec3(1.000, 0.914, 0.659); // #ffe9a8
  vec3 cWhite  = vec3(1.000, 1.000, 0.950); // white-hot
  vec3 cCool   = vec3(0.247, 0.890, 0.816); // #3fe3d0 aqua shimmer

  vec3 c = mix(cDark, cGold, smoothstep(0.0, 0.45, heat));
  c = mix(c, cBright, smoothstep(0.42, 0.78, heat));
  c = mix(c, cWhite, smoothstep(0.78, 1.0, heat) * uHot);
  c = mix(c, cCool, uCool * smoothstep(0.45, 1.0, heat) * 0.6);

  // Rim emission so the core edges glow into the corona.
  float fres = pow(1.0 - max(dot(vNormalV, vViewDir), 0.0), 2.0);
  c += cBright * fres * 0.5;

  c *= uBrightness * uFlicker;
  gl_FragColor = vec4(c, 1.0);
}
`;

const CORONA_VERT = /* glsl */ `
varying vec3 vNormalV;
varying vec3 vViewDir;
void main() {
  vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
  vNormalV = normalize(normalMatrix * normal);
  vViewDir = normalize(-mvPosition.xyz);
  gl_Position = projectionMatrix * mvPosition;
}
`;

const CORONA_FRAG = /* glsl */ `
precision highp float;
varying vec3 vNormalV;
varying vec3 vViewDir;
uniform float uBrightness;
uniform float uCool;
void main() {
  float fres = pow(1.0 - max(dot(vNormalV, vViewDir), 0.0), 2.5);
  vec3 cGold   = vec3(1.000, 0.760, 0.278);
  vec3 cBright = vec3(1.000, 0.914, 0.659);
  vec3 cCool   = vec3(0.247, 0.890, 0.816);
  vec3 c = mix(cGold, cBright, fres);
  c = mix(c, cCool, uCool * 0.5);
  gl_FragColor = vec4(c * fres * uBrightness, fres);
}
`;

export function HelixOrb({ voiceState, audioLevel }: OrbProps) {
  // --- Core + corona meshes (imperative so we can drive uniforms per-frame) -
  const meshes = useMemo(() => {
    // Icosahedron with high detail gives an even vertex spread for smooth
    // surface displacement. Geometry radius = 1; scaled via mesh.scale.
    const coreGeo = new IcosahedronGeometry(1, 6);
    const coronaGeo = new IcosahedronGeometry(1, 3);

    const coreMat = new ShaderMaterial({
      uniforms: {
        uTime: { value: 0 },
        uBrightness: { value: STATE_PARAMS.idle.brightness },
        uHot: { value: STATE_PARAMS.idle.hot },
        uCool: { value: STATE_PARAMS.idle.cool },
        uFlicker: { value: 1 },
        uNoiseScale: { value: 1.8 },
        uDisplace: { value: 0.06 },
      },
      vertexShader: CORE_VERT,
      fragmentShader: CORE_FRAG,
    });

    const coronaMat = new ShaderMaterial({
      uniforms: {
        uBrightness: { value: STATE_PARAMS.idle.brightness },
        uCool: { value: STATE_PARAMS.idle.cool },
      },
      vertexShader: CORONA_VERT,
      fragmentShader: CORONA_FRAG,
      transparent: true,
      blending: AdditiveBlending,
      depthWrite: false,
      side: BackSide, // render the far shell so it haloes behind the core
    });

    const core = new Mesh(coreGeo, coreMat);
    const corona = new Mesh(coronaGeo, coronaMat);
    return { core, corona, coreMat, coronaMat };
  }, []);

  // --- Runtime state refs ---------------------------------------------------
  const params = useRef({ ...STATE_PARAMS.idle });
  const flowTime = useRef(0); // accumulated noise-flow time (turbulence-scaled)
  const flickerVal = useRef(1);
  const nextFlickerTime = useRef(0.1);

  useFrame((state, delta) => {
    const t = state.clock.elapsedTime;
    const target = STATE_PARAMS[voiceState];
    const k = Math.min(1, delta * 2.5);

    // 1. Lerp the behaviour knobs toward the current state's targets.
    const p = params.current;
    p.scale += (target.scale - p.scale) * k;
    p.brightness += (target.brightness - p.brightness) * k;
    p.turbulence += (target.turbulence - p.turbulence) * k;
    p.hot += (target.hot - p.hot) * k;
    p.cool += (target.cool - p.cool) * k;

    const speaking = voiceState === "speaking";
    const pulse = speaking ? audioLevel : 0;

    // 2. Advance noise flow — faster turbulence rolls the fire harder.
    flowTime.current += delta * (0.4 + p.turbulence);

    // 3. Fire flicker — random dips with quick recovery; louder/thinking = more.
    nextFlickerTime.current -= delta;
    if (nextFlickerTime.current <= 0) {
      const amp =
        0.12 + (speaking ? pulse * 0.3 : 0) + (voiceState === "thinking" ? 0.1 : 0);
      flickerVal.current = 1 - Math.random() * amp;
      nextFlickerTime.current = 0.04 + Math.random() * 0.12;
    } else {
      flickerVal.current += (1 - flickerVal.current) * Math.min(1, delta * 10);
    }

    // 4. Live brightness/scale, with the speaking-state audio pulse on top.
    const liveBright = p.brightness + pulse * 0.4;
    const liveScale = p.scale + pulse * 0.18;
    const breath = 1 + 0.03 * Math.sin(t * 1.5);
    const coreScale = BASE_RADIUS * liveScale * breath;

    // 5. Push uniforms.
    const cu = meshes.coreMat.uniforms;
    cu.uTime.value = flowTime.current;
    cu.uBrightness.value = liveBright;
    cu.uHot.value = Math.min(1.2, p.hot + pulse * 0.3);
    cu.uCool.value = p.cool;
    cu.uFlicker.value = flickerVal.current;
    cu.uDisplace.value = 0.04 + p.turbulence * 0.045;

    const xu = meshes.coronaMat.uniforms;
    xu.uBrightness.value = liveBright * 0.9 + pulse * 0.2;
    xu.uCool.value = p.cool;

    // 6. Scale + slow roll.
    meshes.core.scale.setScalar(coreScale);
    meshes.corona.scale.setScalar(coreScale * CORONA_SCALE);
    meshes.core.rotation.y += delta * 0.05;
  });

  return (
    <group>
      <primitive object={meshes.corona} />
      <primitive object={meshes.core} />
    </group>
  );
}

export default HelixOrb;
