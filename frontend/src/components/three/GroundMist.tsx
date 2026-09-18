"use client";

/**
 * A soft, slowly-scrolling noise band hugging the forest floor. Two
 * overlapping planes at different scales/speeds avoid the "obviously
 * tiling" look a single noise plane gets at this size.
 */

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import { mistFragmentShader, mistVertexShader } from "./shaders";

interface GroundMistProps {
  width?: number;
  reducedMotion?: boolean;
}

function MistLayer({
  width,
  height,
  y,
  opacity,
  reducedMotion,
}: {
  width: number;
  height: number;
  y: number;
  opacity: number;
  reducedMotion: boolean;
}) {
  const materialRef = useRef<THREE.ShaderMaterial>(null);
  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uColor: { value: new THREE.Color("#cfe9db") },
    }),
    []
  );
  useFrame((_, delta) => {
    if (!reducedMotion && materialRef.current) materialRef.current.uniforms.uTime!.value += delta;
  });
  return (
    <mesh position={[0, y, -width * 0.1]} rotation={[0, 0, 0]}>
      <planeGeometry args={[width, height]} />
      <shaderMaterial
        ref={materialRef}
        vertexShader={mistVertexShader}
        fragmentShader={mistFragmentShader}
        uniforms={uniforms}
        transparent
        depthWrite={false}
        opacity={opacity}
      />
    </mesh>
  );
}

export function GroundMist({ width = 60, reducedMotion = false }: GroundMistProps) {
  return (
    <group>
      <MistLayer width={width} height={4.5} y={0.4} opacity={0.9} reducedMotion={reducedMotion} />
      <MistLayer
        width={width * 0.8}
        height={3}
        y={0.9}
        opacity={0.55}
        reducedMotion={reducedMotion}
      />
    </group>
  );
}
