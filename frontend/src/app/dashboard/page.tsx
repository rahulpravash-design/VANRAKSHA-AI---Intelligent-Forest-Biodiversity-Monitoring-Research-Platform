"use client";

import Link from "next/link";

import { SpeciesOrbitClient as SpeciesOrbit } from "@/components/three/SpeciesOrbitClient";
import { AsyncBoundary } from "@/components/ui/AsyncBoundary";
import { Card, CardHeader } from "@/components/ui/Card";
import { ConfidenceMeter } from "@/components/ui/ConfidenceMeter";
import { StatTile } from "@/components/ui/StatTile";
import { VerificationBadge } from "@/components/ui/Badge";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { AppShell } from "@/components/layout/AppShell";
import { useAsync } from "@/hooks/useAsync";
import { analyticsApi, observationsApi } from "@/lib/endpoints";
import { formatDateTime, formatNumber, formatPercent } from "@/lib/format";
import { useAuthStore } from "@/lib/auth-store";

function DashboardContent() {
  const user = useAuthStore((state) => state.user);
  const overview = useAsync(() => analyticsApi.overview(), []);
  const recent = useAsync(() => observationsApi.list({ limit: 6, sort: "-created_at" }), []);

  return (
    <AppShell title={`Welcome back, ${user?.full_name?.split(" ")[0] ?? ""}`}>
      <AsyncBoundary loading={overview.loading} error={overview.error} data={overview.data}>
        {(data) => (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <StatTile label="Species catalogued" value={formatNumber(data.species_total)} hint={`${data.species_observed} observed`} />
              <StatTile label="Observations" value={formatNumber(data.observations_total)} hint={`${data.observations_last_30_days} in last 30 days`} />
              <StatTile
                label="Verified"
                value={formatPercent(data.observations_verified / Math.max(data.observations_total, 1))}
                hint={`${data.observations_pending} pending review`}
              />
              <StatTile label="Open alerts" value={formatNumber(data.open_alerts)} hint={`${data.devices_active} active sensors`} />
            </div>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
              <Card className="lg:col-span-2">
                <CardHeader
                  title="Biodiversity by category"
                  subtitle="Each orbiting node is one species category, sized by catalogue count"
                />
                <div className="h-64">
                  <SpeciesOrbit categories={data.species_by_category} className="h-full w-full" />
                </div>
              </Card>

              <Card className="lg:col-span-3">
                <CardHeader
                  title="Recent observations"
                  action={
                    <Link href="/observations" className="text-xs font-medium text-amber-glow-soft hover:underline">
                      View all →
                    </Link>
                  }
                />
                <AsyncBoundary loading={recent.loading} error={recent.error} data={recent.data?.items ?? null}>
                  {(items) => (
                    <ul className="divide-y divide-canopy-800">
                      {items.map((observation) => (
                        <li key={observation.id} className="flex items-center justify-between gap-3 py-3">
                          <div className="min-w-0">
                            <Link
                              href={`/observations/${observation.id}`}
                              className="truncate text-sm font-medium text-canopy-50 hover:text-amber-glow-soft"
                            >
                              {observation.species?.common_name ?? observation.ai_prediction ?? "Unidentified"}
                            </Link>
                            <p className="text-xs text-canopy-400">
                              {observation.zone_name ?? "Unassigned zone"} · {formatDateTime(observation.observed_at)}
                            </p>
                          </div>
                          <div className="flex shrink-0 items-center gap-3">
                            <ConfidenceMeter
                              confidence={observation.ai_confidence}
                              isUncertain={observation.ai_prediction === "UNCERTAIN" || !observation.ai_prediction}
                            />
                            <VerificationBadge status={observation.verification_status} />
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </AsyncBoundary>
              </Card>
            </div>

            <p className="text-xs text-canopy-500">{data.disclaimer}</p>
          </div>
        )}
      </AsyncBoundary>
    </AppShell>
  );
}

export default function DashboardPage() {
  return (
    <RequireAuth>
      <DashboardContent />
    </RequireAuth>
  );
}
