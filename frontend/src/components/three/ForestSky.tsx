"use client";

/**
 * Lighting rig with a slow day↔dusk cycle: a "sun" directional light and
 * the scene fog both interpolate between a cool dawn tone and a warm dusk
 * tone over roughly a minute, driven by a single 0..1 phase so nothing can
 * drift out of sync.
 */

import { useFrame, useThree } from "@react-three/fiber";
import { useRef } from "react";
import * as THREE from "three";

interface ForestSkyProps {
  reducedMotion?: boolean;
  cycleSeconds?: number;
}

const DAWN = new THREE.Color("#8fd6c9");
const DUSK = new THREE.Color("#f2b544");
const DAWN_FOG = new THREE.Color("#0f2e24");
const DUSK_FOG = new THREE.Color("#1c2a1f");

export function ForestSky({ reducedMotion = false, cycleSeconds = 50 }: ForestSkyProps) {
  const lightRef = useRef<THREE.DirectionalLight>(null);
  const { scene } = useThree();

  useFrame((state) => {
    const phase = reducedMotion
      ? 0.5
      : (Math.sin((state.clock.elapsedTime / cycleSeconds) * Math.PI * 2) + 1) / 2;

    if (lightRef.current) {
      lightRef.current.color.copy(DAWN).lerp(DUSK, phase);
      lightRef.current.intensity = 1.1 + phase * 0.6;
      lightRef.current.position.set(
        Math.cos(phase * Math.PI) * 14,
        10 + phase * 4,
        6 - phase * 8
      );
    }
    if (scene.fog instanceof THREE.Fog) {
      const fogColor = DAWN_FOG.clone().lerp(DUSK_FOG, phase);
      scene.fog.color.copy(fogColor);
    }
  });

  return (
    <>
      <ambientLight intensity={0.55} color="#bfe3d1" />
      <directionalLight ref={lightRef} position={[8, 12, 4]} intensity={1.2} color={DAWN} castShadow />
      <hemisphereLight args={["#3f9670", "#0b1f19", 0.6]} />
    </>
  );
}
