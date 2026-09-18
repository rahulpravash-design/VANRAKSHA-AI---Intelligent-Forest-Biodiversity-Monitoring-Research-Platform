"use client";

/**
 * A slow, autonomous camera drift — an orbit too gentle to call "spinning",
 * meant to read as "the scene is alive" without ever distracting from the
 * content overlaid on top of it. Disabled entirely under reduced-motion.
 */

import { useFrame, useThree } from "@react-three/fiber";
import { useRef } from "react";
import * as THREE from "three";

interface CameraDriftProps {
  radius?: number;
  height?: number;
  speed?: number;
  reducedMotion?: boolean;
}

export function CameraDrift({
  radius = 12,
  height = 3.2,
  speed = 0.045,
  reducedMotion = false,
}: CameraDriftProps) {
  const { camera } = useThree();
  const target = useRef(new THREE.Vector3(0, 2.2, -4));

  useFrame((state) => {
    if (reducedMotion) {
      camera.position.set(0, height, radius);
      camera.lookAt(target.current);
      return;
    }
    const t = state.clock.elapsedTime * speed;
    camera.position.x = Math.sin(t) * radius * 0.35;
    camera.position.y = height + Math.sin(t * 0.6) * 0.4;
    camera.position.z = radius + Math.cos(t) * radius * 0.15;
    camera.lookAt(target.current);
  });

  return null;
}
