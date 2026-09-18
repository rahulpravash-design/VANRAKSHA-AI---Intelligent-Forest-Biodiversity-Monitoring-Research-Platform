"use client";

/**
 * A 3D orbit visualization driven by real data: one glowing node per species
 * category, sized by how many species the catalogue holds in it and
 * orbiting a central "biodiversity core" at a speed proportional to how
 * recently that category was detected. This is the dashboard's compact 3D
 * widget — unlike ForestHero, it exists specifically to visualise
 * `OverviewCounts.species_by_category` rather than to set a mood, so it
 * changes shape as the deployment's own data grows.
 */

import { Html } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

const CATEGORY_COLOR: Record<string, string> = {
  MAMMAL: "#f2b544",
  BIRD: "#67b992",
  PLANT: "#3f9670",
  REPTILE: "#c98a4b",
  AMPHIBIAN: "#56b6c2",
  INSECT: "#e0a8d8",
  FUNGI: "#b3895a",
  OTHER: "#a1d9bc",
};

interface OrbitNodeProps {
  label: string;
  count: number;
  radius: number;
  speed: number;
  phase: number;
  maxCount: number;
}

function OrbitNode({ label, count, radius, speed, phase, maxCount }: OrbitNodeProps) {
  const groupRef = useRef<THREE.Group>(null);
  const color = CATEGORY_COLOR[label] ?? "#a1d9bc";
  const size = 0.16 + (count / Math.max(maxCount, 1)) * 0.34;

  useFrame((state) => {
    const t = state.clock.elapsedTime * speed + phase;
    if (groupRef.current) {
      groupRef.current.position.set(Math.cos(t) * radius, Math.sin(t * 0.6) * 0.6, Math.sin(t) * radius);
    }
  });

  return (
    <group ref={groupRef}>
      <mesh>
        <sphereGeometry args={[size, 20, 20]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={0.55}
          roughness={0.35}
        />
      </mesh>
      <Html distanceFactor={9} center>
        <div className="pointer-events-none select-none whitespace-nowrap rounded-full bg-canopy-950/80 px-2 py-0.5 text-[10px] font-medium text-canopy-50 shadow-canopy">
          {label.charAt(0) + label.slice(1).toLowerCase()} · {count}
        </div>
      </Html>
    </group>
  );
}

function OrbitRings({ radii }: { radii: number[] }) {
  return (
    <>
      {radii.map((radius) => (
        <mesh key={radius} rotation={[Math.PI / 2, 0, 0]}>
          <ringGeometry args={[radius - 0.01, radius + 0.01, 64]} />
          <meshBasicMaterial color="#1f5641" transparent opacity={0.35} side={THREE.DoubleSide} />
        </mesh>
      ))}
    </>
  );
}

function Core() {
  const meshRef = useRef<THREE.Mesh>(null);
  useFrame((_, delta) => {
    if (meshRef.current) meshRef.current.rotation.y += delta * 0.15;
  });
  return (
    <mesh ref={meshRef}>
      <icosahedronGeometry args={[0.55, 1]} />
      <meshStandardMaterial
        color="#2c7355"
        emissive="#f2b544"
        emissiveIntensity={0.25}
        roughness={0.4}
        wireframe
      />
    </mesh>
  );
}

interface SpeciesOrbitProps {
  categories: Record<string, number>;
  className?: string;
}

export function SpeciesOrbit({ categories, className }: SpeciesOrbitProps) {
  const entries = useMemo(() => Object.entries(categories).filter(([, count]) => count > 0), [
    categories,
  ]);
  const maxCount = useMemo(
    () => Math.max(...entries.map(([, count]) => count), 1),
    [entries]
  );
  const radii = useMemo(
    () => entries.map((_, index) => 1.5 + index * 0.55),
    [entries]
  );

  if (entries.length === 0) {
    return (
      <div className={`${className ?? ""} flex items-center justify-center text-sm text-canopy-300`}>
        No species recorded yet.
      </div>
    );
  }

  return (
    <div className={className}>
      <Canvas
        camera={{ fov: 42, position: [0, 3.5, 7] }}
        dpr={[1, 1.5]}
        gl={{ alpha: true }}
        // A transparent clear colour, not a "transparent" THREE.Color (which
        // is not a valid colour value and silently produced an opaque white
        // canvas instead) — this is what actually lets the dark card
        // background show through behind the orbit.
        onCreated={({ gl }) => gl.setClearColor(0x000000, 0)}
      >
        <ambientLight intensity={0.7} />
        <pointLight position={[4, 4, 4]} intensity={40} color="#f2b544" />
        <Core />
        <OrbitRings radii={radii} />
        {entries.map(([label, count], index) => (
          <OrbitNode
            key={label}
            label={label}
            count={count}
            radius={radii[index]!}
            speed={0.18 + (index % 3) * 0.05}
            phase={index * 1.3}
            maxCount={maxCount}
          />
        ))}
      </Canvas>
    </div>
  );
}
