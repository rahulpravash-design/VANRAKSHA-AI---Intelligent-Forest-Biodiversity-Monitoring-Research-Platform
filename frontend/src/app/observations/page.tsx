"use client";

import Link from "next/link";
import { useState } from "react";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { AsyncBoundary } from "@/components/ui/AsyncBoundary";
import { Badge, VerificationBadge } from "@/components/ui/Badge";
import { LinkButton } from "@/components/ui/Button";
import { ConfidenceMeter } from "@/components/ui/ConfidenceMeter";
import { Field, Input, Label, Select } from "@/components/ui/Field";
import { useAsync } from "@/hooks/useAsync";
import { mediaUrl } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import { observationsApi } from "@/lib/endpoints";
import { formatDateTime } from "@/lib/format";
import type { VerificationStatus } from "@/lib/types";

const TYPE_ICON: Record<string, string> = {
  IMAGE: "📷",
  AUDIO: "🎙️",
  MULTIMODAL: "🔗",
  FIELD_NOTE: "📝",
  CAMERA_TRAP: "📸",
  SENSOR: "📡",
};

function ObservationsContent() {
  const capabilities = useAuthStore((state) => state.capabilities);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<VerificationStatus | "">("");
  const [page, setPage] = useState(0);
  const limit = 20;

  const observations = useAsync(
    () =>
      observationsApi.list({
        search: search || undefined,
        verification_status: status || undefined,
        limit,
        offset: page * limit,
      }),
    [search, status, page]
  );

  return (
    <AppShell title="Observations">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap items-end gap-3">
          <Field className="w-56">
            <Label htmlFor="search">Search</Label>
            <Input
              id="search"
              placeholder="Species, notes…"
              value={search}
              onChange={(event) => {
                setPage(0);
                setSearch(event.target.value);
              }}
            />
          </Field>
          <Field className="w-48">
            <Label htmlFor="status">Verification status</Label>
            <Select
              id="status"
              value={status}
              onChange={(event) => {
                setPage(0);
                setStatus(event.target.value as VerificationStatus | "");
              }}
            >
              <option value="">All statuses</option>
              <option value="PENDING">Pending</option>
              <option value="CONFIRMED">Confirmed</option>
              <option value="CORRECTED">Corrected</option>
              <option value="REJECTED">Rejected</option>
              <option value="UNCERTAIN">Uncertain</option>
            </Select>
          </Field>
        </div>
        {capabilities?.can_record_observations ? (
          <LinkButton href="/observations/new">+ New observation</LinkButton>
        ) : null}
      </div>

      <AsyncBoundary
        loading={observations.loading}
        error={observations.error}
        data={observations.data?.items ?? null}
        empty={<p className="py-12 text-center text-sm text-canopy-400">No observations match these filters.</p>}
      >
        {(items) => (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((observation) => (
              <Link
                key={observation.id}
                href={`/observations/${observation.id}`}
                className="group overflow-hidden rounded-xl border border-canopy-700/60 bg-canopy-900/60 transition-colors hover:border-amber-glow/50"
              >
                <div className="relative flex h-36 items-center justify-center overflow-hidden bg-canopy-800">
                  {observation.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={mediaUrl(observation.image_url)}
                      alt=""
                      className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                    />
                  ) : (
                    <span className="text-4xl opacity-70">
                      {TYPE_ICON[observation.observation_type] ?? "📝"}
                    </span>
                  )}
                  <div className="absolute right-2 top-2">
                    <VerificationBadge status={observation.verification_status} />
                  </div>
                </div>
                <div className="p-3">
                  <p className="truncate text-sm font-semibold text-canopy-50">
                    {observation.species?.common_name ?? observation.ai_prediction ?? "Unidentified"}
                  </p>
                  <p className="mt-0.5 text-xs text-canopy-400">
                    {observation.zone_name ?? "Unassigned"} · {formatDateTime(observation.observed_at)}
                  </p>
                  <div className="mt-2 flex items-center justify-between">
                    <ConfidenceMeter
                      confidence={observation.ai_confidence}
                      isUncertain={!observation.ai_prediction || observation.ai_prediction === "UNCERTAIN"}
                    />
                    {observation.location_generalised ? (
                      <Badge tone="gray">Location generalised</Badge>
                    ) : null}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </AsyncBoundary>

      {observations.data ? (
        <div className="mt-6 flex items-center justify-between text-xs text-canopy-400">
          <span>
            {observations.data.total} total · page {page + 1}
          </span>
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
              disabled={(page + 1) * limit >= observations.data.total}
              onClick={() => setPage((value) => value + 1)}
              className="rounded border border-canopy-700 px-3 py-1 disabled:opacity-30"
            >
              Next
            </button>
          </div>
        </div>
      ) : null}
    </AppShell>
  );
}

export default function ObservationsPage() {
  return (
    <RequireAuth>
      <ObservationsContent />
    </RequireAuth>
  );
}
