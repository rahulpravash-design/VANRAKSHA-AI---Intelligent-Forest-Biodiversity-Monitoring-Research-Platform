"use client";

import dynamic from "next/dynamic";

const SpeciesOrbit = dynamic(() => import("./SpeciesOrbit").then((mod) => mod.SpeciesOrbit), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center text-xs text-canopy-400">
      Loading visualization…
    </div>
  ),
});

export { SpeciesOrbit as SpeciesOrbitClient };
