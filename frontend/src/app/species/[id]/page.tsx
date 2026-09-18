"use client";

import { useParams, useRouter } from "next/navigation";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { AsyncBoundary } from "@/components/ui/AsyncBoundary";
import { Badge, ConservationBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { StatTile } from "@/components/ui/StatTile";
import { useAsync } from "@/hooks/useAsync";
import { speciesApi } from "@/lib/endpoints";
import { formatDate, formatNumber } from "@/lib/format";

function SpeciesDetailContent() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = Number(params.id);
  const species = useAsync(() => speciesApi.get(id), [id]);

  return (
    <AppShell title="Species profile">
      <AsyncBoundary loading={species.loading} error={species.error} data={species.data}>
        {(data) => (
          <div className="mx-auto max-w-3xl space-y-6">
            <Card>
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="neutral">{data.category}</Badge>
                <ConservationBadge status={data.conservation_status} />
                {data.is_location_sensitive ? <Badge tone="red">Location-sensitive</Badge> : null}
              </div>
              <h1 className="mt-3 font-display text-2xl font-semibold text-canopy-50">
                {data.common_name}
              </h1>
              <p className="text-sm italic text-canopy-300">{data.scientific_name}</p>
              {data.family ? (
                <p className="mt-1 text-xs text-canopy-400">
                  Family: {data.family}
                  {data.genus ? ` · Genus: ${data.genus}` : ""}
                </p>
              ) : null}
              {data.description ? (
                <p className="mt-4 text-sm leading-relaxed text-canopy-200">{data.description}</p>
              ) : null}
              {data.habitat ? (
                <p className="mt-2 text-sm text-canopy-300">
                  <span className="font-medium text-canopy-100">Habitat: </span>
                  {data.habitat}
                </p>
              ) : null}
            </Card>

            <div className="grid grid-cols-3 gap-4">
              <StatTile label="Total detections" value={formatNumber(data.observation_count)} />
              <StatTile label="Verified" value={formatNumber(data.verified_observation_count)} />
              <StatTile label="Last detected" value={formatDate(data.last_observed_at)} />
            </div>

            {data.research_notes ? (
              <Card>
                <CardHeader title="Research notes" />
                <pre className="overflow-x-auto whitespace-pre-wrap break-words text-xs text-canopy-300">
                  {JSON.stringify(data.research_notes, null, 2)}
                </pre>
              </Card>
            ) : null}

            <Button variant="secondary" onClick={() => router.back()}>
              ← Back
            </Button>
          </div>
        )}
      </AsyncBoundary>
    </AppShell>
  );
}

export default function SpeciesDetailPage() {
  return (
    <RequireAuth>
      <SpeciesDetailContent />
    </RequireAuth>
  );
}
