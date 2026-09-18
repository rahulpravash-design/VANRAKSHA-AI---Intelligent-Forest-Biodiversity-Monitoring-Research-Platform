"use client";

import Link from "next/link";
import { useState } from "react";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth, RequireCapability } from "@/components/layout/RequireAuth";
import { AsyncBoundary } from "@/components/ui/AsyncBoundary";
import { Badge } from "@/components/ui/Badge";
import { Card, CardHeader } from "@/components/ui/Card";
import { ConfidenceMeter } from "@/components/ui/ConfidenceMeter";
import { StatTile } from "@/components/ui/StatTile";
import { useAsync } from "@/hooks/useAsync";
import { mediaUrl } from "@/lib/api";
import { verificationApi } from "@/lib/endpoints";
import { formatPercent } from "@/lib/format";

function VerificationContent() {
  const [page, setPage] = useState(0);
  const limit = 15;
  const queue = useAsync(() => verificationApi.queue({ limit, offset: page * limit }), [page]);
  const stats = useAsync(() => verificationApi.stats(), []);

  return (
    <AppShell title="Expert verification">
      <div className="space-y-6">
        <AsyncBoundary loading={stats.loading} error={stats.error} data={stats.data}>
          {(data) => (
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
              <StatTile label="Reviewed" value={data.reviewed_count} />
              <StatTile label="Confirmed" value={data.confirmed} />
              <StatTile label="Corrected" value={data.corrected} />
              <StatTile label="Rejected" value={data.rejected} />
              <StatTile label="AI agreement" value={formatPercent(data.ai_agreement_rate)} hint={data.note} />
            </div>
          )}
        </AsyncBoundary>

        <Card>
          <CardHeader
            title="Review queue"
            subtitle="Oldest first — records are never abandoned by a newest-first queue."
          />
          <AsyncBoundary
            loading={queue.loading}
            error={queue.error}
            data={queue.data?.items ?? null}
            empty={<p className="py-10 text-center text-sm text-canopy-400">Nothing pending review. 🎉</p>}
          >
            {(items) => (
              <ul className="divide-y divide-canopy-800">
                {items.map((item) => (
                  <li key={item.observation.id} className="flex items-center gap-4 py-4">
                    <div className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-canopy-800">
                      {item.observation.image_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={mediaUrl(item.observation.image_url)} alt="" className="h-full w-full object-cover" />
                      ) : (
                        <span className="text-xl">{item.has_audio ? "🎙️" : "📝"}</span>
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <Link
                        href={`/observations/${item.observation.id}`}
                        className="text-sm font-medium text-canopy-50 hover:text-amber-glow-soft"
                      >
                        {item.reported_species?.common_name ?? "No species reported"}
                      </Link>
                      <p className="text-xs text-canopy-400">
                        AI: {item.ai_predicted_label ?? "—"} · waiting {item.waiting_days.toFixed(1)}d
                      </p>
                    </div>
                    <ConfidenceMeter confidence={item.ai_confidence} isUncertain={!item.ai_predicted_label} />
                    <Badge tone="amber">Pending</Badge>
                  </li>
                ))}
              </ul>
            )}
          </AsyncBoundary>

          {queue.data ? (
            <div className="mt-4 flex items-center justify-between text-xs text-canopy-400">
              <span>{queue.data.total} pending</span>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={page === 0}
                  onClick={() => setPage((value) => Math.max(0, value - 1))}
                  className="rounded border border-canopy-700 px-3 py-1 disabled:opacity-30"
                >
                  Previous
                </button>
                <button
                  type="button"
                  disabled={(page + 1) * limit >= queue.data.total}
                  onClick={() => setPage((value) => value + 1)}
                  className="rounded border border-canopy-700 px-3 py-1 disabled:opacity-30"
                >
                  Next
                </button>
              </div>
            </div>
          ) : null}
        </Card>
      </div>
    </AppShell>
  );
}

export default function VerificationPage() {
  return (
    <RequireAuth>
      <RequireCapability capability="can_verify">
        <VerificationContent />
      </RequireCapability>
    </RequireAuth>
  );
}
