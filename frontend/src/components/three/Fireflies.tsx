"use client";

/**
 * A drifting cloud of glowing point sprites over the canopy — the one
 * "obviously alive" element that reads as biodiversity at a glance rather
 * than as generic particle decoration. Each firefly meanders on a slow,
 * per-point Lissajous-like path computed in JS (cheap at this particle
 * count) while the shader handles the glow and pulse.
 */

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import { mulberry32 } from "./random";
import { fireflyFragmentShader, fireflyVertexShader } from "./shaders";

interface FirefliesProps {
  count?: number;
  bounds?: { x: number; y: [number, number]; z: number };
  reducedMotion?: boolean;
}

export function Fireflies({
  count = 60,
  bounds = { x: 16, y: [0.4, 4.2], z: 16 },
  reducedMotion = false,
}: FirefliesProps) {
  const pointsRef = useRef<THREE.Points>(null);
  const materialRef = useRef<THREE.ShaderMaterial>(null);

  const { geometry, origins, speeds } = useMemo(() => {
    const positions = new Float32Array(count * 3);
    const phases = new Float32Array(count);
    const sizes = new Float32Array(count);
    const originArray = new Float32Array(count * 3);
    const speedArray = new Float32Array(count * 3);

    const rng = mulberry32(count * 104729 + 7);
    for (let i = 0; i < count; i += 1) {
      const x = (rng() - 0.5) * bounds.x * 2;
      const y = THREE.MathUtils.lerp(bounds.y[0], bounds.y[1], rng());
      const z = (rng() - 0.5) * bounds.z * 2 - bounds.z * 0.2;
      positions[i * 3] = x;
      positions[i * 3 + 1] = y;
      positions[i * 3 + 2] = z;
      originArray[i * 3] = x;
      originArray[i * 3 + 1] = y;
      originArray[i * 3 + 2] = z;
      speedArray[i * 3] = 0.15 + rng() * 0.25;
      speedArray[i * 3 + 1] = 0.1 + rng() * 0.2;
      speedArray[i * 3 + 2] = 0.12 + rng() * 0.22;
      phases[i] = rng() * Math.PI * 2;
      sizes[i] = 3.0 + rng() * 3.5;
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geo.setAttribute("aPhase", new THREE.BufferAttribute(phases, 1));
    geo.setAttribute("aSize", new THREE.BufferAttribute(sizes, 1));
    return { geometry: geo, origins: originArray, speeds: speedArray };
  }, [count, bounds]);

  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uColor: { value: new THREE.Color("#ffd76a") },
    }),
    []
  );

  useFrame((state, delta) => {
    if (materialRef.current) materialRef.current.uniforms.uTime!.value += delta;
    if (reducedMotion || !pointsRef.current) return;
    const position = pointsRef.current.geometry.attributes.position as THREE.BufferAttribute;
    const t = state.clock.elapsedTime;
    for (let i = 0; i < count; i += 1) {
      const idx = i * 3;
      position.array[idx] = origins[idx]! + Math.sin(t * speeds[idx]! + i) * 1.4;
      position.array[idx + 1] =
        origins[idx + 1]! + Math.sin(t * speeds[idx + 1]! + i * 1.7) * 0.5;
      position.array[idx + 2] =
        origins[idx + 2]! + Math.cos(t * speeds[idx + 2]! + i * 0.8) * 1.4;
    }
    position.needsUpdate = true;
  });

  return (
    <points ref={pointsRef} geometry={geometry}>
      <shaderMaterial
        ref={materialRef}
        vertexShader={fireflyVertexShader}
        fragmentShader={fireflyFragmentShader}
        uniforms={uniforms}
        transparent
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}
