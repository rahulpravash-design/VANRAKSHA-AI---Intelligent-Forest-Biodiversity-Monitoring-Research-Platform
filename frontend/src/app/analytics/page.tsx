"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useState } from "react";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { AsyncBoundary } from "@/components/ui/AsyncBoundary";
import { Card, CardHeader } from "@/components/ui/Card";
import { StatTile } from "@/components/ui/StatTile";
import { useAsync } from "@/hooks/useAsync";
import { API_BASE } from "@/lib/config";
import { readStoredTokens } from "@/lib/api";
import { analyticsApi } from "@/lib/endpoints";
import { formatNumber, formatPercent } from "@/lib/format";

const CATEGORY_COLORS = ["#f2b544", "#67b992", "#3f9670", "#c98a4b", "#56b6c2", "#e0a8d8", "#b3895a"];
const CHART_TEXT = "#a1d9bc";
const GRID = "#163f32";

function ChartTooltip(props: { active?: boolean; payload?: { name: string; value: number }[]; label?: string }) {
  if (!props.active || !props.payload?.length) return null;
  return (
    <div className="rounded-lg border border-canopy-700 bg-canopy-900 px-3 py-2 text-xs text-canopy-100 shadow-canopy">
      {props.label ? <p className="mb-1 font-semibold">{props.label}</p> : null}
      {props.payload.map((entry) => (
        <p key={entry.name}>
          {entry.name}: {entry.value}
        </p>
      ))}
    </div>
  );
}

function ExportCsvLink() {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function download() {
    setDownloading(true);
    setError(null);
    try {
      // A plain <a href> cannot carry the Authorization header this endpoint
      // requires, so the CSV is fetched through the authenticated client and
      // handed to the browser as a blob download instead.
      const tokens = readStoredTokens();
      const response = await fetch(`${API_BASE}${analyticsApi.exportCsvUrl(true)}`, {
        headers: tokens ? { Authorization: `Bearer ${tokens.access_token}` } : undefined,
      });
      if (!response.ok) throw new Error(`Export failed (${response.status})`);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `vanraksha-observations-${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch {
      setError("Could not export the dataset.");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div>
      <button
        type="button"
        onClick={download}
        disabled={downloading}
        className="text-xs font-medium text-amber-glow-soft hover:underline disabled:opacity-50"
      >
        ⬇ {downloading ? "Preparing…" : "Export verified observations as CSV"}
      </button>
      {error ? <p className="mt-1 text-xs text-alert-critical">{error}</p> : null}
    </div>
  );
}

function AnalyticsContent() {
  const overview = useAsync(() => analyticsApi.overview(), []);
  const trends = useAsync(() => analyticsApi.trends({ granularity: "month" }), []);
  const frequency = useAsync(() => analyticsApi.speciesFrequency({ limit: 8 }), []);
  const diversity = useAsync(() => analyticsApi.diversity(), []);
  const zones = useAsync(() => analyticsApi.zones(), []);
  const seasonal = useAsync(() => analyticsApi.seasonal(), []);

  return (
    <AppShell title="Analytics">
      <div className="space-y-6">
        <AsyncBoundary loading={overview.loading} error={overview.error} data={overview.data}>
          {(data) => (
            <>
              <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                <StatTile label="Detections total" value={formatNumber(data.observations_total)} />
                <StatTile label="AI predictions" value={formatNumber(data.ai_predictions_total)} hint={`${formatPercent(data.ai_uncertain_share)} uncertain`} />
                <StatTile label="New species this month" value={formatNumber(data.new_species_this_month)} />
                <StatTile label="Zones monitored" value={formatNumber(data.zones_total)} />
              </div>
              <p className="text-xs text-canopy-500">{data.disclaimer}</p>
            </>
          )}
        </AsyncBoundary>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader title="Detection trend" subtitle="Observations per month, all zones" />
            <AsyncBoundary loading={trends.loading} error={trends.error} data={trends.data?.points ?? null}>
              {(points) => (
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={points}>
                    <CartesianGrid stroke={GRID} strokeDasharray="3 3" />
                    <XAxis dataKey="period" stroke={CHART_TEXT} fontSize={11} />
                    <YAxis stroke={CHART_TEXT} fontSize={11} allowDecimals={false} />
                    <Tooltip content={<ChartTooltip />} />
                    <Line type="monotone" dataKey="observations" stroke="#f2b544" strokeWidth={2} dot={false} name="Observations" />
                    <Line type="monotone" dataKey="verified" stroke="#3f9670" strokeWidth={2} dot={false} name="Verified" />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </AsyncBoundary>
          </Card>

          <Card>
            <CardHeader title="Most-detected species" subtitle="Share of total detections" />
            <AsyncBoundary loading={frequency.loading} error={frequency.error} data={frequency.data ?? null}>
              {(items) => (
                <ResponsiveContainer width="100%" height={240}>
                  <PieChart>
                    <Pie
                      data={items}
                      dataKey="detections"
                      nameKey="common_name"
                      innerRadius={50}
                      outerRadius={90}
                    >
                      {items.map((entry, index) => (
                        <Cell key={entry.species_id} fill={CATEGORY_COLORS[index % CATEGORY_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip content={<ChartTooltip />} />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </AsyncBoundary>
          </Card>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <Card>
            <CardHeader title="Diversity indices" subtitle="Detection-frequency based" />
            <AsyncBoundary loading={diversity.loading} error={diversity.error} data={diversity.data}>
              {(data) => (
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between"><span className="text-canopy-400">Species richness</span><span>{data.species_richness}</span></div>
                  <div className="flex justify-between"><span className="text-canopy-400">Shannon index</span><span>{data.shannon_index?.toFixed(3) ?? "—"}</span></div>
                  <div className="flex justify-between"><span className="text-canopy-400">Simpson index</span><span>{data.simpson_index?.toFixed(3) ?? "—"}</span></div>
                  <div className="flex justify-between"><span className="text-canopy-400">Chao1 estimate</span><span>{data.chao1_estimate?.toFixed(1) ?? "—"}</span></div>
                  {!data.comparable ? (
                    <p className="mt-2 text-[11px] text-amber-glow-soft">{data.caveat}</p>
                  ) : null}
                </div>
              )}
            </AsyncBoundary>
          </Card>

          <Card className="lg:col-span-2">
            <CardHeader title="Zone comparison" subtitle="Detections per active sampling day" />
            <AsyncBoundary loading={zones.loading} error={zones.error} data={zones.data ?? null}>
              {(items) => (
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={items}>
                    <CartesianGrid stroke={GRID} strokeDasharray="3 3" />
                    <XAxis dataKey="zone_code" stroke={CHART_TEXT} fontSize={11} />
                    <YAxis stroke={CHART_TEXT} fontSize={11} />
                    <Tooltip content={<ChartTooltip />} />
                    <Bar dataKey="detections_per_active_day" fill="#67b992" name="Detections/active day" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </AsyncBoundary>
          </Card>
        </div>

        <Card>
          <CardHeader title="Seasonal pattern" subtitle="Detections by calendar month, across all years" />
          <AsyncBoundary loading={seasonal.loading} error={seasonal.error} data={seasonal.data?.buckets ?? null}>
            {(buckets) => (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={buckets}>
                  <CartesianGrid stroke={GRID} strokeDasharray="3 3" />
                  <XAxis dataKey="month_name" stroke={CHART_TEXT} fontSize={11} />
                  <YAxis stroke={CHART_TEXT} fontSize={11} allowDecimals={false} />
                  <Tooltip content={<ChartTooltip />} />
                  <Bar dataKey="observations" fill="#f2b544" name="Observations" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </AsyncBoundary>
        </Card>

        <ExportCsvLink />
      </div>
    </AppShell>
  );
}

export default function AnalyticsPage() {
  return (
    <RequireAuth>
      <AnalyticsContent />
    </RequireAuth>
  );
}
