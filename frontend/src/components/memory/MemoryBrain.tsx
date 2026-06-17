/**
 * MemoryBrain — the contents of the Memory window's R3F <Canvas>: lights, the
 * glowing core, the neuron cloud, orbit/zoom controls, and a premium bloom
 * pass. The window is OPAQUE (#08080a), so full-screen bloom is safe here
 * (unlike the transparent orb window — do NOT add bloom there).
 */

import { type RefObject } from "react";
import { OrbitControls } from "@react-three/drei";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import type { MemoryEdge, MemoryNode } from "../../lib/types";
import MemoryCore from "./MemoryCore";
import Neurons from "./Neurons";

interface MemoryBrainProps {
  nodes: MemoryNode[];
  edges: MemoryEdge[];
  visibleIds: Set<string> | null;
  panelRef: RefObject<HTMLDivElement | null>;
  onHover: (node: MemoryNode | null) => void;
}

export default function MemoryBrain({ nodes, edges, visibleIds, panelRef, onHover }: MemoryBrainProps) {
  return (
    <>
      <ambientLight intensity={0.45} />
      <pointLight position={[0, 0, 0]} intensity={1.4} color="#ffc247" distance={12} />
      <directionalLight position={[3, 4, 5]} intensity={0.35} color="#ffffff" />

      <MemoryCore />
      {nodes.length > 0 && (
        <Neurons
          nodes={nodes}
          edges={edges}
          visibleIds={visibleIds}
          panelRef={panelRef}
          onHover={onHover}
        />
      )}

      <OrbitControls
        enablePan={false}
        enableDamping
        dampingFactor={0.08}
        rotateSpeed={0.6}
        zoomSpeed={0.8}
        minDistance={3}
        maxDistance={16}
        autoRotate
        autoRotateSpeed={0.35}
      />

      <EffectComposer>
        <Bloom
          intensity={1.25}
          luminanceThreshold={0.18}
          luminanceSmoothing={0.9}
          radius={0.7}
          mipmapBlur
        />
      </EffectComposer>
    </>
  );
}
