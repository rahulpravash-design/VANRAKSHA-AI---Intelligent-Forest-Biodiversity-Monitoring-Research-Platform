"use client";

import { useState } from "react";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth, RequireCapability } from "@/components/layout/RequireAuth";
import { InlineAlert } from "@/components/ui/Alert";
import { AsyncBoundary } from "@/components/ui/AsyncBoundary";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Field, Input, Select, Textarea } from "@/components/ui/Field";
import { useAsync } from "@/hooks/useAsync";
import { ApiError } from "@/lib/api";
import { researchApi } from "@/lib/endpoints";
import type { ExperimentReport } from "@/lib/types";

function CreateExperimentForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [question, setQuestion] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      await researchApi.create(name, question);
      setName("");
      setQuestion("");
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the experiment.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader title="Define an experiment" />
      {error ? <InlineAlert tone="error">{error}</InlineAlert> : null}
      <div className="space-y-3">
        <Field>
          <Input placeholder="Experiment name" value={name} onChange={(event) => setName(event.target.value)} />
        </Field>
        <Field>
          <Textarea
            rows={2}
            placeholder="Research question, e.g. Does combining image and acoustic evidence improve identification over image alone?"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
          />
        </Field>
        <Button onClick={submit} loading={submitting} disabled={!name || question.length < 10}>
          Create
        </Button>
      </div>
    </Card>
  );
}

function ExperimentRunner({ experimentId, onRun }: { experimentId: number; onRun: (report: ExperimentReport) => void }) {
  const [dataset, setDataset] = useState<"synthetic" | "verified">("synthetic");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      const report = await researchApi.run(experimentId, { dataset, sample_count: 160 });
      onRun(report);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The run failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      <Select value={dataset} onChange={(event) => setDataset(event.target.value as typeof dataset)} className="w-40">
        <option value="synthetic">Synthetic benchmark</option>
        <option value="verified">Verified field data</option>
      </Select>
      <Button size="sm" onClick={run} loading={running}>
        Run comparison
      </Button>
      {error ? <span className="text-xs text-alert-critical">{error}</span> : null}
    </div>
  );
}

function ReportView({ report }: { report: ExperimentReport }) {
  return (
    <div className="mt-4 space-y-3 border-t border-canopy-800 pt-4">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-canopy-400">
            <th className="pb-2">Variant</th>
            <th className="pb-2">Macro F1</th>
            <th className="pb-2">mAP</th>
            <th className="pb-2">Coverage</th>
            <th className="pb-2">ECE</th>
          </tr>
        </thead>
        <tbody>
          {report.comparisons.map((row) => (
            <tr key={row.variant} className={row.variant === report.best_variant ? "text-amber-glow-soft" : "text-canopy-200"}>
              <td className="py-1">{row.variant}</td>
              <td>{row.macro_f1.toFixed(3)}</td>
              <td>{row.mean_average_precision.toFixed(3)}</td>
              <td>{(1 - row.uncertain_share).toFixed(3)}</td>
              <td>{row.expected_calibration_error.toFixed(3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs leading-relaxed text-canopy-300">{report.conclusion}</p>
      <p className="text-[11px] italic text-canopy-500">{report.caveat}</p>
    </div>
  );
}

function ResearchContent() {
  const experiments = useAsync(() => researchApi.list(), []);
  const variants = useAsync(() => researchApi.variants(), []);
  const [reports, setReports] = useState<Record<number, ExperimentReport>>({});

  return (
    <AppShell title="Research">
      <div className="space-y-6">
        <AsyncBoundary loading={variants.loading} error={variants.error} data={variants.data}>
          {(data) => (
            <Card>
              <CardHeader title="Verified-data readiness" subtitle="How close this deployment is to a field comparison" />
              <p className="text-sm text-canopy-200">
                {data.verified_dataset.verified_with_media} of the required{" "}
                {data.verified_dataset.minimum_required} expert-verified observations with media
                are available.
              </p>
            </Card>
          )}
        </AsyncBoundary>

        <CreateExperimentForm onCreated={() => experiments.reload()} />

        <AsyncBoundary
          loading={experiments.loading}
          error={experiments.error}
          data={experiments.data}
          empty={<p className="py-8 text-center text-sm text-canopy-400">No experiments defined yet.</p>}
        >
          {(items) => (
            <div className="space-y-4">
              {items.map((experiment) => (
                <Card key={experiment.id}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="text-sm font-semibold text-canopy-50">{experiment.name}</h3>
                      <p className="mt-1 text-xs text-canopy-300">{experiment.research_question}</p>
                    </div>
                    <Badge tone="neutral">{experiment.status}</Badge>
                  </div>
                  <div className="mt-3">
                    <ExperimentRunner
                      experimentId={experiment.id}
                      onRun={(report) => setReports((prev) => ({ ...prev, [experiment.id]: report }))}
                    />
                  </div>
                  {reports[experiment.id] ? <ReportView report={reports[experiment.id]!} /> : null}
                </Card>
              ))}
            </div>
          )}
        </AsyncBoundary>
      </div>
    </AppShell>
  );
}

export default function ResearchPage() {
  return (
    <RequireAuth>
      <RequireCapability capability="can_run_experiments">
        <ResearchContent />
      </RequireCapability>
    </RequireAuth>
  );
}
