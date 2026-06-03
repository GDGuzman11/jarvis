import { useRef } from "react";

export function useBootSound() {
  const fired = useRef(false);

  if (fired.current) return;
  fired.current = true;

  try {
    const ctx = new AudioContext();

    const play = () => {
      // Tone 1: 440 Hz (A4) — primary hit
      const osc1 = ctx.createOscillator();
      const gain1 = ctx.createGain();
      osc1.connect(gain1);
      gain1.connect(ctx.destination);
      osc1.type = "sine";
      osc1.frequency.value = 440;
      gain1.gain.setValueAtTime(0, ctx.currentTime);
      gain1.gain.linearRampToValueAtTime(0.14, ctx.currentTime + 0.016);
      gain1.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.26);
      osc1.start(ctx.currentTime);
      osc1.stop(ctx.currentTime + 0.26);

      // Tone 2: 880 Hz (A5) — harmonic tail, slight overlap
      const osc2 = ctx.createOscillator();
      const gain2 = ctx.createGain();
      osc2.connect(gain2);
      gain2.connect(ctx.destination);
      osc2.type = "sine";
      osc2.frequency.value = 880;
      gain2.gain.setValueAtTime(0, ctx.currentTime + 0.18);
      gain2.gain.linearRampToValueAtTime(0.12, ctx.currentTime + 0.22);
      gain2.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.42);
      osc2.start(ctx.currentTime + 0.18);
      osc2.stop(ctx.currentTime + 0.42);

      setTimeout(() => ctx.close(), 600);
    };

    if (ctx.state === "suspended") {
      ctx.resume().then(play);
    } else {
      play();
    }
  } catch {
    // AudioContext unavailable — silent fail
  }
}
