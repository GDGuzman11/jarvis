---
name: bloom-transparency-constraint
description: When postprocessing bloom is allowed vs forbidden across Helix's Tauri windows (transparency rule).
metadata:
  type: project
---

Bloom (`@react-three/postprocessing` EffectComposer/Bloom) is allowed ONLY in OPAQUE Tauri windows, never in transparent ones.

**Why:** A full-screen postprocessing pass forces an opaque backing buffer, which destroys Tauri window transparency. The orb (`HelixOrb`/`AnimationWindow`, `transparent: true`) deliberately fakes its glow with additive sprites/points + emissive materials instead of bloom to stay truly transparent on the desktop. The Memory window (Window 6, `transparent: false`, `#08080a`) is opaque, so real bloom is safe and approved there.

**How to apply:** Do NOT add bloom/EffectComposer to AnimationWindow or any `transparent: true` window — fake glow with additive blending. Bloom is fine in opaque windows (MemoryWindow). `@react-three/postprocessing` is installed (v3.0.4) as of Phase 16F.
