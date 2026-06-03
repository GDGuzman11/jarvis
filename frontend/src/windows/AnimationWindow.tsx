/**
 * Window 1 — AnimationWindow. Full-bleed Three.js orb that reacts to the live
 * voice state and audio amplitude from the store. The window itself is
 * frameless/transparent in Tauri, so the orb floats on the desktop.
 */

import { Canvas } from "@react-three/fiber";
import { useStore } from "../lib/store";
import { useBootSound } from "../lib/useBootSound";
import JarvisOrb from "../components/JarvisOrb";

const STATE_LABEL: Record<string, string> = {
  idle: "STANDBY",
  listening: "LISTENING",
  thinking: "PROCESSING",
  speaking: "SPEAKING",
};

export function AnimationWindow() {
  useBootSound();
  const voiceState = useStore((s) => s.voiceState);
  const audioLevel = useStore((s) => s.audioLevel);

  return (
    <div className="relative h-screen w-screen bg-jarvis-bg">
      <Canvas camera={{ position: [0, 0, 4], fov: 50 }} dpr={[1, 2]}>
        <JarvisOrb voiceState={voiceState} audioLevel={audioLevel} />
      </Canvas>
      <div className="pointer-events-none absolute inset-x-0 bottom-6 flex justify-center">
        <span className="text-xs font-semibold uppercase tracking-[0.5em] text-glow-cyan">
          {STATE_LABEL[voiceState] ?? voiceState}
        </span>
      </div>
    </div>
  );
}

export default AnimationWindow;
