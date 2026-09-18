"use client";

import { useState } from "react";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { BiodiversityMapClient as BiodiversityMap } from "@/components/map/BiodiversityMapClient";
import { AsyncBoundary } from "@/components/ui/AsyncBoundary";
import { Badge } from "@/components/ui/Badge";
import { useAsync } from "@/hooks/useAsync";
import { zonesApi } from "@/lib/endpoints";

function MapContent() {
  const [selectedZoneId, setSelectedZoneId] = useState<number | null>(null);
  const zones = useAsync(() => zonesApi.list(), []);
  const observations = useAsync(() => zonesApi.observationsGeoJSON({ limit: 3000 }), []);

  return (
    <AppShell title="Biodiversity map">
      <div className="flex h-[calc(100vh-8rem)] flex-col gap-4 lg:flex-row">
        <aside className="w-full shrink-0 overflow-y-auto rounded-xl border border-canopy-700/60 bg-canopy-900/60 p-4 lg:w-64">
          <h3 className="mb-3 font-display text-sm font-semibold text-canopy-50">Forest zones</h3>
          <AsyncBoundary loading={zones.loading} error={zones.error} data={zones.data}>
            {(items) => (
              <ul className="space-y-1">
                <li>
                  <button
                    type="button"
                    onClick={() => setSelectedZoneId(null)}
                    className={`w-full rounded-lg px-3 py-2 text-left text-xs ${
                      selectedZoneId === null ? "bg-canopy-700 text-canopy-50" : "text-canopy-300 hover:bg-canopy-800"
                    }`}
                  >
                    All zones
                  </button>
                </li>
                {items.map((zone) => (
                  <li key={zone.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedZoneId(zone.id)}
                      className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs ${
                        selectedZoneId === zone.id
                          ? "bg-canopy-700 text-canopy-50"
                          : "text-canopy-300 hover:bg-canopy-800"
                      }`}
                    >
                      <span className="truncate">{zone.name}</span>
                      <Badge tone="neutral">{zone.observation_count}</Badge>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </AsyncBoundary>
          {observations.data?.location_generalised ? (
            <p className="mt-4 text-[11px] leading-relaxed text-canopy-500">
              Some markers show generalised coordinates because they belong to
              a threatened or sensitivity-flagged species.
            </p>
          ) : null}
        </aside>
        <div className="min-h-0 flex-1 overflow-hidden rounded-xl border border-canopy-700/60">
          <BiodiversityMap
            zones={zones.data ?? []}
            observations={observations.data ?? null}
            selectedZoneId={selectedZoneId}
          />
        </div>
      </div>
    </AppShell>
  );
}

export default function MapPage() {
  return (
    <RequireAuth>
      <MapContent />
    </RequireAuth>
  );
}
