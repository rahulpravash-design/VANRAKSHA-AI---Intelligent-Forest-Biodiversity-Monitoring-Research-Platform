"use client";

import dynamic from "next/dynamic";

import { Spinner } from "@/components/ui/Button";

const BiodiversityMap = dynamic(
  () => import("./BiodiversityMap").then((mod) => mod.BiodiversityMap),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full items-center justify-center gap-2 text-canopy-300">
        <Spinner /> Loading map…
      </div>
    ),
  }
);

export { BiodiversityMap as BiodiversityMapClient };
