"use client";

/**
 * The forest silhouette: hundreds of instanced low-poly conifers, each
 * swaying independently in a wind field driven entirely on the GPU (see
 * shaders.ts). Built as one InstancedBufferGeometry rather than hundreds of
 * separate meshes — that keeps a "field" of trees to a single draw call.
 *
 * Trees are stylised (a cone for foliage, a short cylinder for a trunk) and
 * placed in a jittered ring layout: denser and larger near the camera,
 * sparser and smaller — with more of the "lit" canopy tint — toward the
 * horizon, which reads as atmospheric depth without needing real fog
 * geometry per tree.
 */

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import { mulberry32 } from "./random";
import { canopyFragmentShader, canopyVertexShader } from "./shaders";

interface CanopyFieldProps {
  count?: number;
  radius?: number;
  windStrength?: number;
  reducedMotion?: boolean;
}

function buildInstancedGeometry(count: number, radius: number) {
  const base = new THREE.ConeGeometry(0.55, 1.6, 7);
  base.translate(0, 0.8, 0);
  const geometry = new THREE.InstancedBufferGeometry();
  geometry.index = base.index;
  geometry.attributes.position = base.attributes.position!;
  geometry.attributes.normal = base.attributes.normal!;

  const offsets = new Float32Array(count * 3);
  const phases = new Float32Array(count);
  const scales = new Float32Array(count);
  const colors = new Float32Array(count * 3);

  const rng = mulberry32(20260917);
  for (let i = 0; i < count; i += 1) {
    // Jittered rings rather than a uniform disc, so density thins out
    // smoothly toward the horizon instead of stopping at a hard edge.
    const t = i / count;
    const ringRadius = radius * (0.08 + Math.pow(t, 0.62) * 0.98);
    const angle = rng() * Math.PI * 2;
    const jitterR = ringRadius + (rng() - 0.5) * radius * 0.06;
    const x = Math.cos(angle) * jitterR;
    const z = Math.sin(angle) * jitterR - radius * 0.15;
    const depth = jitterR / radius;
    const scale = THREE.MathUtils.lerp(1.35, 0.35, depth) * (0.75 + rng() * 0.5);

    offsets[i * 3] = x;
    offsets[i * 3 + 1] = -0.15 - rng() * 0.05;
    offsets[i * 3 + 2] = z;
    phases[i] = rng() * Math.PI * 2;
    scales[i] = scale;

    // Nearby trees read as a deeper, saturated green; distant ones fade
    // toward the mist tint — the vertex color feeds the shader's lit/deep mix.
    const green = THREE.MathUtils.lerp(0.85, 0.35, depth);
    colors[i * 3] = green * 0.4;
    colors[i * 3 + 1] = green;
    colors[i * 3 + 2] = green * 0.55;
  }

  geometry.setAttribute("instanceOffset", new THREE.InstancedBufferAttribute(offsets, 3));
  geometry.setAttribute("instancePhase", new THREE.InstancedBufferAttribute(phases, 1));
  geometry.setAttribute("instanceScale", new THREE.InstancedBufferAttribute(scales, 1));
  geometry.setAttribute("color", new THREE.InstancedBufferAttribute(colors, 3));
  geometry.instanceCount = count;

  const boundingSphereRadius = radius * 1.2;
  geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0, 0), boundingSphereRadius);

  return geometry;
}

export function CanopyField({
  count = 420,
  radius = 26,
  windStrength = 0.22,
  reducedMotion = false,
}: CanopyFieldProps) {
  const geometry = useMemo(() => buildInstancedGeometry(count, radius), [count, radius]);
  const materialRef = useRef<THREE.ShaderMaterial>(null);

  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uWindStrength: { value: reducedMotion ? 0 : windStrength },
      uDeepColor: { value: new THREE.Color("#0b241c") },
      uLitColor: { value: new THREE.Color("#3f9670") },
    }),
    [windStrength, reducedMotion]
  );

  useFrame((_, delta) => {
    if (reducedMotion) return;
    const material = materialRef.current;
    if (material) material.uniforms.uTime!.value += delta;
  });

  return (
    <mesh geometry={geometry} frustumCulled={false} castShadow receiveShadow>
      <shaderMaterial
        ref={materialRef}
        vertexShader={canopyVertexShader}
        fragmentShader={canopyFragmentShader}
        uniforms={uniforms}
        vertexColors
      />
    </mesh>
  );
}
