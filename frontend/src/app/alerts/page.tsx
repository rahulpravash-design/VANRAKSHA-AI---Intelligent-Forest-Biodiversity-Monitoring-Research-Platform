"use client";

import { useState } from "react";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { InlineAlert } from "@/components/ui/Alert";
import { AsyncBoundary } from "@/components/ui/AsyncBoundary";
import { Badge, SeverityBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, Select, Textarea } from "@/components/ui/Field";
import { useAsync } from "@/hooks/useAsync";
import { ApiError } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import { alertsApi } from "@/lib/endpoints";
import { formatDateTime } from "@/lib/format";
import type { AlertRead, AlertStatus } from "@/lib/types";

const STATUS_TONE: Record<AlertStatus, "amber" | "blue" | "green" | "gray"> = {
  OPEN: "amber",
  INVESTIGATING: "blue",
  RESOLVED: "green",
  DISMISSED: "gray",
};

function AlertRow({ alert, canManage, onChanged }: { alert: AlertRead; canManage: boolean; onChanged: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [notes, setNotes] = useState("");
  const [cause, setCause] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function updateStatus(status: AlertStatus) {
    if ((status === "RESOLVED" || status === "DISMISSED") && !notes.trim()) {
      setError("Closing an alert requires resolution notes describing what was found.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await alertsApi.update(alert.id, {
        status,
        resolution_notes: notes || undefined,
        confirmed_cause: cause || undefined,
      });
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update the alert.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <SeverityBadge severity={alert.severity} />
            <Badge tone={STATUS_TONE[alert.status]}>{alert.status}</Badge>
            {alert.zone_name ? <Badge tone="neutral">{alert.zone_name}</Badge> : null}
          </div>
          <h3 className="mt-2 text-sm font-semibold text-canopy-50">{alert.title}</h3>
          <p className="mt-1 text-xs leading-relaxed text-canopy-300">{alert.message}</p>
          <p className="mt-1 text-[11px] text-canopy-500">{formatDateTime(alert.detected_at)}</p>
        </div>
        {canManage && alert.status !== "RESOLVED" && alert.status !== "DISMISSED" ? (
          <Button variant="secondary" size="sm" onClick={() => setExpanded((value) => !value)}>
            {expanded ? "Close" : "Investigate"}
          </Button>
        ) : null}
      </div>

      {alert.candidate_causes && alert.candidate_causes.length > 0 ? (
        <div className="mt-3">
          <p className="text-[11px] font-medium text-canopy-400">Candidate causes (not a conclusion):</p>
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {alert.candidate_causes.map((causeItem) => (
              <li key={causeItem}>
                <Badge tone="gray">{causeItem}</Badge>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {alert.confirmed_cause ? (
        <p className="mt-3 text-xs text-canopy-200">
          <span className="font-medium">Confirmed cause: </span>
          {alert.confirmed_cause} — {alert.resolution_notes}
        </p>
      ) : null}

      {expanded ? (
        <div className="mt-4 space-y-3 border-t border-canopy-800 pt-4">
          {error ? <InlineAlert tone="error">{error}</InlineAlert> : null}
          {alert.status === "OPEN" ? (
            <Button size="sm" variant="secondary" onClick={() => updateStatus("INVESTIGATING")} loading={submitting}>
              Mark as investigating
            </Button>
          ) : null}
          <Field>
            <Textarea
              rows={2}
              placeholder="What did you find in the field? (required to close)"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
          </Field>
          <Field>
            <Select value={cause} onChange={(event) => setCause(event.target.value)}>
              <option value="">Confirmed cause (optional)</option>
              {alert.candidate_causes?.map((causeItem) => (
                <option key={causeItem} value={causeItem}>
                  {causeItem}
                </option>
              ))}
              <option value="Other">Other</option>
            </Select>
          </Field>
          <div className="flex gap-2">
            <Button size="sm" onClick={() => updateStatus("RESOLVED")} loading={submitting}>
              Resolve
            </Button>
            <Button size="sm" variant="danger" onClick={() => updateStatus("DISMISSED")} loading={submitting}>
              Dismiss
            </Button>
          </div>
        </div>
      ) : null}
    </Card>
  );
}

function AlertsContent() {
  const capabilities = useAuthStore((state) => state.capabilities);
  const [status, setStatus] = useState<AlertStatus | "">("");
  const alerts = useAsync(() => alertsApi.list({ status: status || undefined, limit: 50 }), [status]);

  return (
    <AppShell title="Alerts">
      <div className="mb-4 flex items-center justify-between">
        <Field className="w-52">
          <Select value={status} onChange={(event) => setStatus(event.target.value as AlertStatus | "")}>
            <option value="">All statuses</option>
            <option value="OPEN">Open</option>
            <option value="INVESTIGATING">Investigating</option>
            <option value="RESOLVED">Resolved</option>
            <option value="DISMISSED">Dismissed</option>
          </Select>
        </Field>
        {capabilities?.can_manage_alerts ? (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => alertsApi.detect().then(() => alerts.reload())}
          >
            Run anomaly detection
          </Button>
        ) : null}
      </div>

      <AsyncBoundary
        loading={alerts.loading}
        error={alerts.error}
        data={alerts.data?.items ?? null}
        empty={<p className="py-10 text-center text-sm text-canopy-400">No alerts. The forest is quiet. 🌿</p>}
      >
        {(items) => (
          <div className="space-y-4">
            {items.map((alert) => (
              <AlertRow
                key={alert.id}
                alert={alert}
                canManage={Boolean(capabilities?.can_manage_alerts)}
                onChanged={() => alerts.reload()}
              />
            ))}
          </div>
        )}
      </AsyncBoundary>
    </AppShell>
  );
}

export default function AlertsPage() {
  return (
    <RequireAuth>
      <AlertsContent />
    </RequireAuth>
  );
}
