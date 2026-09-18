"use client";

/**
 * Client-only wrapper around ForestHero. `next/dynamic`'s `ssr: false`
 * option can only be used from a Client Component, so this one-line
 * indirection is what lets the landing page itself stay a (fast, SEO-
 * friendly) Server Component while the WebGL canvas still never touches
 * the server render.
 */

import dynamic from "next/dynamic";

const ForestHero = dynamic(() => import("./ForestHero").then((mod) => mod.ForestHero), {
  ssr: false,
});

export { ForestHero as ForestHeroClient };
