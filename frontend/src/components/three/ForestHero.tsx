"use client";

/**
 * The 3D hero scene: an animated forest canopy with wind-swayed trees,
 * drifting fireflies, scrolling ground mist, a slow dawn↔dusk lighting
 * cycle, and a gentle autonomous camera drift.
 *
 * Deliberately built from scratch (custom GLSL shaders, hand-rolled
 * instancing) rather than a stock "3D background" package, so the scene
 * reads as *this platform's* forest rather than a generic Three.js demo —
 * and so it stays inspectable and cheap: one draw call for several hundred
 * trees, a few hundred point sprites for fireflies, two mist planes.
 *
 * Respects `prefers-reduced-motion`: animation (wind, fireflies, camera
 * drift, day/night cycle) is switched off entirely rather than merely
 * slowed, and the canvas still renders a complete, static forest.
 */

import { Canvas } from "@react-three/fiber";
import { Suspense, useEffect, useState } from "react";
import * as THREE from "three";

import { CameraDrift } from "./CameraDrift";
import { CanopyField } from "./CanopyField";
import { Fireflies } from "./Fireflies";
import { ForestSky } from "./ForestSky";
import { GroundMist } from "./GroundMist";

function useReducedMotion(): boolean {
  // This component is only ever mounted client-side (see ForestHeroClient's
  // `ssr: false`), so reading matchMedia in the lazy initializer is safe and
  // avoids the extra render a synchronous setState-in-effect would cause.
  const [reduced, setReduced] = useState(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const listener = (event: MediaQueryListEvent) => setReduced(event.matches);
    query.addEventListener("change", listener);
    return () => query.removeEventListener("change", listener);
  }, []);
  return reduced;
}

interface ForestHeroProps {
  className?: string;
  /** Lower density for smaller/secondary placements of the scene. */
  density?: "full" | "compact";
}

export function ForestHero({ className, density = "full" }: ForestHeroProps) {
  const reducedMotion = useReducedMotion();
  const isCompact = density === "compact";

  return (
    <div className={className} aria-hidden="true">
      <Canvas
        dpr={[1, 1.75]}
        gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
        camera={{ fov: 45, near: 0.1, far: 120, position: [0, 3.2, 12] }}
        onCreated={({ scene }) => {
          scene.fog = new THREE.Fog(new THREE.Color("#0f2e24"), 8, isCompact ? 26 : 38);
        }}
      >
        <color attach="background" args={["#071310"]} />
        <Suspense fallback={null}>
          <ForestSky reducedMotion={reducedMotion} />
          <CanopyField
            count={isCompact ? 180 : 420}
            radius={isCompact ? 16 : 26}
            reducedMotion={reducedMotion}
          />
          <GroundMist width={isCompact ? 34 : 60} reducedMotion={reducedMotion} />
          <Fireflies count={isCompact ? 28 : 60} reducedMotion={reducedMotion} />
          <CameraDrift reducedMotion={reducedMotion} radius={isCompact ? 9 : 12} />
        </Suspense>
      </Canvas>
    </div>
  );
}
