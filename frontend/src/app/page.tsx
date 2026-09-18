import Link from "next/link";

import { ForestHeroClient as ForestHero } from "@/components/three/ForestHeroClient";
import { LinkButton } from "@/components/ui/Button";

const PIPELINE = [
  { step: "Capture", detail: "Photograph, record, or log a field observation." },
  { step: "Identify", detail: "AI-assisted image, audio, or fused identification." },
  { step: "Verify", detail: "A qualified expert confirms or corrects the call." },
  { step: "Geotag", detail: "Location-aware storage, privacy-generalised for sensitive taxa." },
  { step: "Store", detail: "A growing, attributable biodiversity dataset." },
  { step: "Analyze", detail: "Trends, diversity indices, zone comparisons." },
  { step: "Detect anomalies", detail: "Unusual patterns flagged for investigation, never diagnosed." },
  { step: "Research", detail: "Modality comparisons on one identical, seeded split." },
];

const MODULES = [
  {
    title: "Computer vision",
    body: "A descriptor-based baseline ships by default; drop in trained YOLO weights when ready — no code change.",
    icon: "📷",
  },
  {
    title: "Acoustic AI",
    body: "Mel-spectrogram feature extraction and template matching identify calls from field recordings.",
    icon: "🎙️",
  },
  {
    title: "Multimodal fusion",
    body: "Reliability-weighted log-linear pooling combines image and audio evidence — tested, not assumed.",
    icon: "🔗",
  },
  {
    title: "GIS & privacy",
    body: "Interactive zone and observation maps, with automatic coordinate generalisation for sensitive species.",
    icon: "🗺️",
  },
  {
    title: "Anomaly detection",
    body: "A robust statistical baseline plus an Isolation Forest flag unusual patterns for human investigation.",
    icon: "📈",
  },
  {
    title: "Research framework",
    body: "Compare image-only, audio-only and fused identification on one seeded, reproducible split.",
    icon: "🔬",
  },
];

export default function LandingPage() {
  return (
    <main className="relative min-h-screen overflow-x-hidden bg-canopy-950 text-canopy-50">
      <section className="relative flex min-h-screen flex-col overflow-hidden">
        <div className="absolute inset-0">
          <ForestHero className="h-full w-full" />
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-canopy-950/40 via-canopy-950/10 to-canopy-950" />
        </div>

        <nav className="relative z-10 flex items-center justify-between px-6 py-6 lg:px-12">
          <div className="flex items-center gap-2">
            <span className="text-2xl">🌳</span>
            <span className="font-display text-lg font-semibold tracking-wide">VANRAKSHA AI</span>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/login"
              className="rounded-lg px-4 py-2 text-sm font-medium text-canopy-100 hover:text-amber-glow-soft"
            >
              Sign in
            </Link>
            <LinkButton href="/register" size="sm">
              Get started
            </LinkButton>
          </div>
        </nav>

        <div className="relative z-10 flex flex-1 flex-col items-center justify-center px-6 text-center">
          <span className="mb-4 inline-flex items-center gap-2 rounded-full border border-canopy-600/60 bg-canopy-900/60 px-3 py-1 text-xs font-medium text-canopy-200 backdrop-blur-sm">
            Intelligent Forest Biodiversity Monitoring &amp; Research Platform
          </span>
          <h1 className="max-w-3xl font-display text-4xl font-bold leading-tight sm:text-5xl lg:text-6xl">
            See the forest.{" "}
            <span className="bg-gradient-to-r from-amber-glow to-canopy-300 bg-clip-text text-transparent">
              Understand every species.
            </span>
          </h1>
          <p className="mt-5 max-w-xl text-balance text-sm text-canopy-200 sm:text-base">
            Capture → AI-assisted identification → expert verification → geotagged
            storage → analytics → unusual-pattern detection → research. Every AI
            output is labelled AI-assisted, never confirmed taxonomy.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <LinkButton href="/register" size="lg">
              Start monitoring
            </LinkButton>
            <LinkButton href="/login" variant="secondary" size="lg">
              Sign in
            </LinkButton>
          </div>
        </div>

        <div className="relative z-10 pb-8 text-center text-xs text-canopy-400">
          Scroll to explore the platform ↓
        </div>
      </section>

      <section className="relative border-t border-canopy-800 bg-canopy-950 px-6 py-20 lg:px-12">
        <div className="mx-auto max-w-5xl">
          <h2 className="text-center font-display text-2xl font-semibold sm:text-3xl">
            The research workflow
          </h2>
          <div className="mt-10 grid grid-cols-2 gap-4 sm:grid-cols-4">
            {PIPELINE.map((item, index) => (
              <div
                key={item.step}
                className="rounded-xl border border-canopy-700/60 bg-canopy-900/50 p-4"
              >
                <span className="font-display text-xs font-semibold text-amber-glow-soft">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <p className="mt-2 text-sm font-semibold text-canopy-50">{item.step}</p>
                <p className="mt-1 text-xs leading-relaxed text-canopy-300">{item.detail}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="relative border-t border-canopy-800 bg-canopy-900/40 px-6 py-20 lg:px-12">
        <div className="mx-auto max-w-6xl">
          <h2 className="text-center font-display text-2xl font-semibold sm:text-3xl">
            Six research-grade modules, one platform
          </h2>
          <div className="mt-10 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {MODULES.map((module) => (
              <div
                key={module.title}
                className="rounded-2xl border border-canopy-700/60 bg-canopy-950/60 p-6"
              >
                <span className="text-2xl">{module.icon}</span>
                <h3 className="mt-3 font-display text-base font-semibold text-canopy-50">
                  {module.title}
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-canopy-300">{module.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="relative border-t border-canopy-800 px-6 py-16 text-center lg:px-12">
        <h2 className="font-display text-2xl font-semibold sm:text-3xl">
          Ready to build your biodiversity dataset?
        </h2>
        <p className="mx-auto mt-3 max-w-xl text-sm text-canopy-300">
          Researchers, forest officers, taxonomic experts and reviewers — every
          role has a workflow here.
        </p>
        <div className="mt-6 flex justify-center gap-3">
          <LinkButton href="/register" size="lg">
            Create an account
          </LinkButton>
        </div>
        <p className="mt-10 text-xs text-canopy-500">
          🌳 VANRAKSHA AI — counts are detections, not population estimates.
        </p>
      </section>
    </main>
  );
}
