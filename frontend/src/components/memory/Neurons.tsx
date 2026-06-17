/**
 * Neurons — the instanced neuron cloud of the memory brain plus its edge and
 * core-tether line sets. One `InstancedMesh` (a glowing sphere per node) and
 * two `LineSegments` (similarity edges + faint core tethers) are driven by the
 * hand-rolled `BrainLayout` sim each frame over typed-array buffers — no
 * per-node React objects, so a few hundred neurons stay at 60fps.
 *
 * Hover uses fiber's instanced raycast (`e.instanceId`): the panel content is
 * reported up via `onHover`, while the panel's screen position is updated
 * imperatively each frame (projecting the live neuron position) so it stays
 * glued to a drifting neuron without re-rendering React 60×/sec.
 */

import { useEffect, useMemo, useRef, type RefObject } from "react";
import { useFrame, type ThreeEvent } from "@react-three/fiber";
import {
  AdditiveBlending,
  BufferGeometry,
  Color,
  Float32BufferAttribute,
  InstancedMesh,
  LineBasicMaterial,
  LineSegments,
  Object3D,
  Vector3,
} from "three";
import type { MemoryEdge, MemoryNode } from "../../lib/types";
import { AQUA, nodeStyle, type NodeStyle } from "../../lib/memoryStyle";
import { BrainLayout, type LayoutEdge } from "../../lib/memoryLayout";
import { useStore } from "../../lib/store";

interface NeuronsProps {
  nodes: MemoryNode[];
  edges: MemoryEdge[];
  /** ids matching the search filter, or null for "show all". */
  visibleIds: Set<string> | null;
  panelRef: RefObject<HTMLDivElement | null>;
  onHover: (node: MemoryNode | null) => void;
}

const dummy = new Object3D();
const scratch = new Vector3();
const col = new Color();
const flashCol = new Color();

/** How long a recalled neuron stays flashed before fully fading (ms). */
const FLASH_MS = 1500;

export default function Neurons({ nodes, edges, visibleIds, panelRef, onHover }: NeuronsProps) {
  const count = nodes.length;
  const meshRef = useRef<InstancedMesh>(null);
  const hitRef = useRef<InstancedMesh>(null);
  const hoverRef = useRef(-1);

  // Stable id → instance index map and precomputed per-node styles.
  const index = useMemo(() => {
    const m = new Map<string, number>();
    nodes.forEach((n, i) => m.set(n.id, i));
    return m;
  }, [nodes]);
  const styles = useMemo<NodeStyle[]>(() => nodes.map(nodeStyle), [nodes]);

  const layoutEdges = useMemo<LayoutEdge[]>(() => {
    const out: LayoutEdge[] = [];
    for (const e of edges) {
      const a = index.get(e.source_id);
      const b = index.get(e.target_id);
      if (a !== undefined && b !== undefined) out.push({ a, b, similarity: e.similarity });
    }
    return out;
  }, [edges, index]);

  // Rebuild the sim when the node count changes; just re-point edges otherwise.
  const layout = useMemo(() => new BrainLayout(count, layoutEdges), [count]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => layout.setEdges(layoutEdges), [layout, layoutEdges]);

  // Edge + tether line buffers (2 verts each), additive vertex-coloured.
  const edgeLines = useMemo(() => makeLines(layoutEdges.length), [layoutEdges.length]);
  const tetherLines = useMemo(() => makeLines(count), [count]);

  // Per-instance flash start times (ms, Date.now()) for recalled neurons. A
  // plain typed array keyed by instance index — no per-neuron React state, so
  // many neurons can flash together at 60fps. Zero = "never flashed".
  const flashStart = useMemo(() => new Float64Array(Math.max(count, 1)), [count]);

  // When Helix recalls facts, stamp the matching neurons' flash start so the
  // useFrame loop pulses them. Re-stamping resets a still-fading flash.
  const recallFlash = useStore((s) => s.recallFlash);
  useEffect(() => {
    if (!recallFlash) return;
    for (const id of recallFlash.ids) {
      const i = index.get(id);
      if (i !== undefined && i < flashStart.length) flashStart[i] = recallFlash.at;
    }
  }, [recallFlash, index, flashStart]);

  useFrame((state, delta) => {
    const mesh = meshRef.current;
    if (!mesh) return;
    const hit = hitRef.current;
    layout.step(delta, state.clock.elapsedTime);
    const p = layout.positions;
    const hovered = hoverRef.current;

    // --- Neuron instances: matrix + colour ---
    const searching = visibleIds !== null;
    const now = Date.now();
    for (let i = 0; i < count; i++) {
      const ix = i * 3;
      const s = styles[i];
      const visible = !searching || visibleIds!.has(nodes[i].id);
      const isHover = i === hovered;
      // A search hit: brighten + enlarge + aqua-tint so it clearly GLOWS,
      // while non-matches dim well back so the hit pops against the cloud.
      const isMatch = searching && visible;
      // Decaying recall flash: 1 right after recall → 0 after FLASH_MS.
      const flash = Math.max(0, 1 - (now - flashStart[i]) / FLASH_MS);
      const pulse = 0.85 + 0.15 * Math.sin(state.clock.elapsedTime * 2 + i);
      const scale =
        (visible ? s.size : s.size * 0.3) *
        (isHover ? 1.7 : isMatch ? 1.45 : 1) *
        (1 + 0.8 * flash) *
        pulse;
      dummy.position.set(p[ix], p[ix + 1], p[ix + 2]);
      dummy.scale.setScalar(scale);
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);

      // Larger invisible hover proxy at the same spot so small neurons are
      // easy to target (the visible neuron keeps its styled size).
      if (hit) {
        dummy.scale.setScalar(Math.max(s.size * 2.8, 0.5) * pulse);
        dummy.updateMatrix();
        hit.setMatrixAt(i, dummy.matrix);
      }

      const baseLum = visible ? (isMatch ? s.glow * 2.0 : s.glow) : 0.08;
      // Recall flash blows brightness up so the neuron reads as white-hot.
      const lum = baseLum * (isHover ? 1.6 : 1) * (1 + 2.5 * flash);
      col.setRGB(s.color[0], s.color[1], s.color[2]).multiplyScalar(lum);
      if (isMatch) col.lerp(col.clone().setRGB(AQUA[0], AQUA[1], AQUA[2]), 0.45);
      else if (s.recalled) col.lerp(col.clone().setRGB(AQUA[0], AQUA[1], AQUA[2]), 0.35);
      // Tint toward a bright white-aqua while flashing (kept HDR-bright so bloom
      // still blooms it). Mixed last so it overrides the base/search hue.
      if (flash > 0) {
        flashCol.setRGB(0.78 * lum, 1.0 * lum, 0.94 * lum);
        col.lerp(flashCol, Math.min(0.85, flash));
      }
      mesh.setColorAt(i, col);
    }
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    if (hit) hit.instanceMatrix.needsUpdate = true;

    // --- Similarity edges ---
    const ep = edgeLines.geometry.attributes.position.array as Float32Array;
    const ec = edgeLines.geometry.attributes.color.array as Float32Array;
    for (let k = 0; k < layoutEdges.length; k++) {
      const e = layoutEdges[k];
      const a = e.a * 3, b = e.b * 3, j = k * 6;
      const vis = (!visibleIds || (visibleIds.has(nodes[e.a].id) && visibleIds.has(nodes[e.b].id))) ? 1 : 0.04;
      const br = (0.1 + (e.similarity - 0.5) * 1.2) * vis;
      ep[j] = p[a]; ep[j + 1] = p[a + 1]; ep[j + 2] = p[a + 2];
      ep[j + 3] = p[b]; ep[j + 4] = p[b + 1]; ep[j + 5] = p[b + 2];
      for (let t = 0; t < 2; t++) {
        ec[j + t * 3] = 1.0 * br; ec[j + t * 3 + 1] = 0.78 * br; ec[j + t * 3 + 2] = 0.36 * br;
      }
    }
    edgeLines.geometry.attributes.position.needsUpdate = true;
    edgeLines.geometry.attributes.color.needsUpdate = true;

    // --- Core tethers (faint, neuron → origin) ---
    const tp = tetherLines.geometry.attributes.position.array as Float32Array;
    const tc = tetherLines.geometry.attributes.color.array as Float32Array;
    for (let i = 0; i < count; i++) {
      const ix = i * 3, j = i * 6;
      tp[j] = p[ix]; tp[j + 1] = p[ix + 1]; tp[j + 2] = p[ix + 2];
      tp[j + 3] = 0; tp[j + 4] = 0; tp[j + 5] = 0;
      tc[j] = 0.05; tc[j + 1] = 0.04; tc[j + 2] = 0.02;
      tc[j + 3] = 0.5; tc[j + 4] = 0.38; tc[j + 5] = 0.14;
    }
    tetherLines.geometry.attributes.position.needsUpdate = true;
    tetherLines.geometry.attributes.color.needsUpdate = true;

    // --- Anchor the hover panel to the live neuron position ---
    const el = panelRef.current;
    if (el) {
      if (hovered >= 0 && hovered < count) {
        const hx = hovered * 3;
        scratch.set(p[hx], p[hx + 1], p[hx + 2]).project(state.camera);
        const w = state.size.width, h = state.size.height;
        const x = (scratch.x * 0.5 + 0.5) * w;
        const y = (-scratch.y * 0.5 + 0.5) * h;
        const pw = el.offsetWidth, ph = el.offsetHeight;
        let tx = x + 18, ty = y - ph / 2;
        if (tx + pw > w - 8) tx = x - pw - 18;
        ty = Math.max(8, Math.min(ty, h - ph - 8));
        el.style.transform = `translate(${tx}px, ${ty}px)`;
        el.style.opacity = scratch.z < 1 ? "1" : "0";
      } else {
        el.style.opacity = "0";
      }
    }
  });

  const setHover = (id: number) => {
    if (hoverRef.current === id) return;
    hoverRef.current = id;
    onHover(id >= 0 && id < count ? nodes[id] : null);
  };

  return (
    <>
      <instancedMesh
        ref={meshRef}
        args={[undefined, undefined, Math.max(count, 1)]}
      >
        <sphereGeometry args={[1, 14, 14]} />
        <meshBasicMaterial toneMapped={false} />
      </instancedMesh>
      {/* Invisible, larger hover proxies — decouple the hit area from the
          visible neuron size so small neurons are still easy to target. */}
      <instancedMesh
        ref={hitRef}
        args={[undefined, undefined, Math.max(count, 1)]}
        onPointerMove={(e: ThreeEvent<PointerEvent>) => {
          e.stopPropagation();
          if (e.instanceId !== undefined) setHover(e.instanceId);
        }}
        onPointerOut={() => setHover(-1)}
      >
        <sphereGeometry args={[1, 10, 10]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </instancedMesh>
      <primitive object={edgeLines} />
      <primitive object={tetherLines} />
    </>
  );
}

/** Build an additive vertex-coloured LineSegments with `n` segments. */
function makeLines(n: number): LineSegments {
  const geo = new BufferGeometry();
  geo.setAttribute("position", new Float32BufferAttribute(new Float32Array(Math.max(n, 1) * 6), 3));
  geo.setAttribute("color", new Float32BufferAttribute(new Float32Array(Math.max(n, 1) * 6), 3));
  const mat = new LineBasicMaterial({
    vertexColors: true,
    transparent: true,
    blending: AdditiveBlending,
    depthWrite: false,
    toneMapped: false,
  });
  const lines = new LineSegments(geo, mat);
  // Lines must never intercept the hover raycast — only the invisible neuron
  // hit-spheres are valid hover targets. Otherwise a line crossing in front of
  // a neuron would steal the pointer and the HUD panel would never appear.
  lines.raycast = () => null;
  return lines;
}
