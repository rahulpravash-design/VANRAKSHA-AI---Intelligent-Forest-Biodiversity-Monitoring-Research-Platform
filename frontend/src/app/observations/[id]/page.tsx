"use client";

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { InlineAlert } from "@/components/ui/Alert";
import { AsyncBoundary } from "@/components/ui/AsyncBoundary";
import { Badge, ConservationBadge, VerificationBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ConfidenceMeter } from "@/components/ui/ConfidenceMeter";
import { Field, Select, Textarea } from "@/components/ui/Field";
import { useAsync } from "@/hooks/useAsync";
import { ApiError, mediaUrl } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import { observationsApi, speciesApi, verificationApi } from "@/lib/endpoints";
import { formatDateTime } from "@/lib/format";
import type { AIPredictionRead, VerificationDecision } from "@/lib/types";

function PredictionCard({ prediction }: { prediction: AIPredictionRead }) {
  return (
    <div className="rounded-lg border border-canopy-700/60 bg-canopy-950/50 p-3">
      <div className="flex items-center justify-between">
        <Badge tone={prediction.modality === "FUSED" ? "amber" : "blue"}>
          {prediction.modality}
        </Badge>
        <span className="text-[11px] text-canopy-500">
          {prediction.model_name}@{prediction.model_version}
        </span>
      </div>
      <p className="mt-2 text-sm font-semibold text-canopy-50">
        {prediction.is_uncertain ? "Uncertain — not identified" : prediction.predicted_label}
      </p>
      <p className="mt-0.5 text-[11px] italic text-canopy-400">{prediction.identification_basis}</p>
      <div className="mt-2">
        <ConfidenceMeter confidence={prediction.confidence} isUncertain={prediction.is_uncertain} />
      </div>
      {prediction.top_k && prediction.top_k.length > 1 ? (
        <ul className="mt-2 space-y-0.5 text-[11px] text-canopy-400">
          {prediction.top_k.slice(1, 4).map((candidate) => (
            <li key={candidate.label}>
              {candidate.label} — {(candidate.confidence * 100).toFixed(0)}%
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function VerifyPanel({ observationId, reportedSpeciesId, onDone }: {
  observationId: number;
  reportedSpeciesId: number | undefined;
  onDone: () => void;
}) {
  // The API caps `limit` at 200 (see backend/app/api/v1/species.py); a
  // higher value here 422s the request and silently empties this dropdown.
  const species = useAsync(() => speciesApi.list({ limit: 200 }), []);
  const [decision, setDecision] = useState<VerificationDecision>("CONFIRM");
  const [correctedId, setCorrectedId] = useState("");
  const [comments, setComments] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      await verificationApi.submit(
        observationId,
        decision,
        decision === "CORRECT" ? Number(correctedId) : undefined,
        comments || undefined
      );
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit the review.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader title="Expert verification" subtitle="Your decision sets this record&apos;s final species." />
      {error ? <InlineAlert tone="error">{error}</InlineAlert> : null}
      <div className="space-y-3">
        <Field>
          <Select value={decision} onChange={(event) => setDecision(event.target.value as VerificationDecision)}>
            <option value="CONFIRM">✅ Confirm reported species</option>
            <option value="CORRECT">✏️ Correct — it&apos;s a different species</option>
            <option value="REJECT">❌ Reject — cannot be identified</option>
            <option value="UNCERTAIN">❔ Uncertain — needs a second opinion</option>
          </Select>
        </Field>
        {decision === "CORRECT" ? (
          <Field>
            <Select value={correctedId} onChange={(event) => setCorrectedId(event.target.value)}>
              <option value="">Select the correct species…</option>
              {(species.data?.items ?? [])
                .filter((item) => item.id !== reportedSpeciesId)
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.common_name} ({item.scientific_name})
                  </option>
                ))}
            </Select>
          </Field>
        ) : null}
        <Field>
          <Textarea
            rows={2}
            placeholder="Comments (optional)"
            value={comments}
            onChange={(event) => setComments(event.target.value)}
          />
        </Field>
        <Button
          className="w-full"
          loading={submitting}
          disabled={decision === "CORRECT" && !correctedId}
          onClick={submit}
        >
          Submit review
        </Button>
      </div>
    </Card>
  );
}

function ObservationDetailContent() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = Number(params.id);
  const capabilities = useAuthStore((state) => state.capabilities);
  const observation = useAsync(() => observationsApi.get(id), [id]);

  return (
    <AppShell title="Observation">
      <AsyncBoundary loading={observation.loading} error={observation.error} data={observation.data}>
        {(data) => (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <div className="space-y-6 lg:col-span-2">
              <Card>
                {data.image_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={mediaUrl(data.image_url)}
                    alt=""
                    className="mb-4 max-h-96 w-full rounded-xl object-cover"
                  />
                ) : null}
                {data.audio_url ? (
                  <div className="mb-4 space-y-2">
                    <audio controls className="w-full" src={mediaUrl(data.audio_url)} />
                    {data.media.find((asset) => asset.kind === "SPECTROGRAM") ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={mediaUrl(
                          data.media.find((asset) => asset.kind === "SPECTROGRAM")!.public_url
                        )}
                        alt="Spectrogram"
                        className="w-full rounded-lg border border-canopy-700"
                      />
                    ) : null}
                  </div>
                ) : null}

                <div className="flex flex-wrap items-center gap-2">
                  <VerificationBadge status={data.verification_status} />
                  {data.final_species ? (
                    <ConservationBadge status={data.final_species.conservation_status} />
                  ) : null}
                  {data.location_generalised ? <Badge tone="gray">Location generalised</Badge> : null}
                </div>

                <h1 className="mt-3 font-display text-2xl font-semibold text-canopy-50">
                  {data.final_species?.common_name ?? data.species?.common_name ?? "Unidentified"}
                </h1>
                {data.final_species?.scientific_name ?? data.species?.scientific_name ? (
                  <p className="text-sm italic text-canopy-300">
                    {data.final_species?.scientific_name ?? data.species?.scientific_name}
                  </p>
                ) : null}

                <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <dt className="text-xs text-canopy-400">Observed</dt>
                    <dd className="text-canopy-100">{formatDateTime(data.observed_at)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-canopy-400">Zone</dt>
                    <dd className="text-canopy-100">{data.zone_name ?? "Unassigned"}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-canopy-400">Recorded by</dt>
                    <dd className="text-canopy-100">{data.researcher?.full_name ?? "—"}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-canopy-400">Coordinates</dt>
                    <dd className="text-canopy-100">
                      {data.latitude && data.longitude
                        ? `${data.latitude.toFixed(4)}, ${data.longitude.toFixed(4)}`
                        : "—"}
                    </dd>
                  </div>
                </dl>
                {data.notes ? (
                  <p className="mt-4 rounded-lg bg-canopy-950/50 p-3 text-sm text-canopy-200">
                    {data.notes}
                  </p>
                ) : null}
              </Card>

              {data.predictions.length > 0 ? (
                <Card>
                  <CardHeader
                    title="AI-assisted identification"
                    subtitle="Every prediction requires expert verification — none of this sets the record's species automatically."
                  />
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {data.predictions.map((prediction) => (
                      <PredictionCard key={prediction.id} prediction={prediction} />
                    ))}
                  </div>
                </Card>
              ) : null}
            </div>

            <div className="space-y-6">
              {capabilities?.can_verify && data.verification_status === "PENDING" ? (
                <VerifyPanel
                  observationId={data.id}
                  reportedSpeciesId={data.species?.id}
                  onDone={() => observation.reload()}
                />
              ) : null}
              {data.verification_status !== "PENDING" ? (
                <Card>
                  <CardHeader title="Review outcome" />
                  <p className="text-sm text-canopy-200">
                    Verified {formatDateTime(data.verified_at)}
                    {data.verified_species ? ` — ${data.verified_species.common_name}` : ""}.
                  </p>
                </Card>
              ) : null}
              <Button variant="secondary" className="w-full" onClick={() => router.back()}>
                ← Back
              </Button>
            </div>
          </div>
        )}
      </AsyncBoundary>
    </AppShell>
  );
}

export default function ObservationDetailPage() {
  return (
    <RequireAuth>
      <ObservationDetailContent />
    </RequireAuth>
  );
}
