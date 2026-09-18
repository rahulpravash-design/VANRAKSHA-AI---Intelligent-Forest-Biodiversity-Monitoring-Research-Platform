"use client";

import Link from "next/link";
import { useState } from "react";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { AsyncBoundary } from "@/components/ui/AsyncBoundary";
import { ConservationBadge, Badge } from "@/components/ui/Badge";
import { Field, Input, Select } from "@/components/ui/Field";
import { useAsync } from "@/hooks/useAsync";
import { speciesApi } from "@/lib/endpoints";
import type { SpeciesCategory } from "@/lib/types";

const CATEGORY_ICON: Record<string, string> = {
  MAMMAL: "🦌",
  BIRD: "🐦",
  PLANT: "🌿",
  REPTILE: "🦎",
  AMPHIBIAN: "🐸",
  INSECT: "🦋",
  FUNGI: "🍄",
  OTHER: "❔",
};

function SpeciesContent() {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<SpeciesCategory | "">("");
  const [threatenedOnly, setThreatenedOnly] = useState(false);

  const species = useAsync(
    () =>
      speciesApi.list({
        search: search || undefined,
        category: category || undefined,
        threatened_only: threatenedOnly || undefined,
        limit: 100,
      }),
    [search, category, threatenedOnly]
  );

  return (
    <AppShell title="Species catalogue">
      <div className="mb-5 flex flex-wrap items-end gap-3">
        <Field className="w-64">
          <Input
            placeholder="Search common or scientific name…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </Field>
        <Field className="w-48">
          <Select value={category} onChange={(event) => setCategory(event.target.value as SpeciesCategory | "")}>
            <option value="">All categories</option>
            <option value="MAMMAL">Mammals</option>
            <option value="BIRD">Birds</option>
            <option value="PLANT">Plants</option>
            <option value="REPTILE">Reptiles</option>
            <option value="AMPHIBIAN">Amphibians</option>
            <option value="INSECT">Insects</option>
          </Select>
        </Field>
        <label className="flex items-center gap-2 pb-2 text-sm text-canopy-200">
          <input
            type="checkbox"
            checked={threatenedOnly}
            onChange={(event) => setThreatenedOnly(event.target.checked)}
            className="h-4 w-4 rounded border-canopy-600 bg-canopy-950 accent-amber-glow"
          />
          Threatened only (CR/EN/VU)
        </label>
      </div>

      <AsyncBoundary loading={species.loading} error={species.error} data={species.data?.items ?? null}>
        {(items) => (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((item) => (
              <Link
                key={item.id}
                href={`/species/${item.id}`}
                className="rounded-xl border border-canopy-700/60 bg-canopy-900/60 p-4 transition-colors hover:border-amber-glow/50"
              >
                <div className="flex items-start justify-between">
                  <span className="text-2xl">{CATEGORY_ICON[item.category] ?? "❔"}</span>
                  {item.is_location_sensitive ? <Badge tone="red">Sensitive</Badge> : null}
                </div>
                <p className="mt-2 font-display text-sm font-semibold text-canopy-50">
                  {item.common_name}
                </p>
                <p className="text-xs italic text-canopy-400">{item.scientific_name}</p>
                <div className="mt-3">
                  <ConservationBadge status={item.conservation_status} />
                </div>
              </Link>
            ))}
          </div>
        )}
      </AsyncBoundary>
    </AppShell>
  );
}

export default function SpeciesPage() {
  return (
    <RequireAuth>
      <SpeciesContent />
    </RequireAuth>
  );
}
