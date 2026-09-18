"use client";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { AsyncBoundary } from "@/components/ui/AsyncBoundary";
import { Badge } from "@/components/ui/Badge";
import { Card, CardHeader } from "@/components/ui/Card";
import { useAsync } from "@/hooks/useAsync";
import { sensorsApi } from "@/lib/endpoints";
import { formatDateTime } from "@/lib/format";
import type { DeviceHealth } from "@/lib/types";

const STATUS_TONE: Record<DeviceHealth["status"], "green" | "amber" | "red" | "gray"> = {
  online: "green",
  late: "amber",
  offline: "red",
  never_reported: "gray",
  disabled: "gray",
};

const KIND_ICON: Record<string, string> = {
  CAMERA_TRAP: "📷",
  ACOUSTIC_RECORDER: "🎙️",
  ENV_SENSOR: "🌡️",
  MULTI_SENSOR_NODE: "📡",
};

function SensorsContent() {
  const health = useAsync(() => sensorsApi.health(), []);

  return (
    <AppShell title="Sensor network">
      <AsyncBoundary
        loading={health.loading}
        error={health.error}
        data={health.data}
        empty={<p className="py-10 text-center text-sm text-canopy-400">No devices registered yet.</p>}
      >
        {(devices) => (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {devices.map((device) => (
              <Card key={device.device_id}>
                <CardHeader
                  title={device.name}
                  subtitle={device.device_code}
                  action={<span className="text-xl">{KIND_ICON[device.kind] ?? "📡"}</span>}
                />
                <div className="flex items-center justify-between text-xs">
                  <Badge tone={STATUS_TONE[device.status]}>{device.status.replace("_", " ")}</Badge>
                  {device.battery_volts ? <span className="text-canopy-400">🔋 {device.battery_volts}V</span> : null}
                </div>
                <dl className="mt-3 space-y-1 text-xs text-canopy-300">
                  <div className="flex justify-between">
                    <dt>Last seen</dt>
                    <dd>{formatDateTime(device.last_seen_at)}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt>Reports every</dt>
                    <dd>{device.report_interval_minutes} min</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt>Readings stored</dt>
                    <dd>{device.reading_count}</dd>
                  </div>
                </dl>
              </Card>
            ))}
          </div>
        )}
      </AsyncBoundary>
    </AppShell>
  );
}

export default function SensorsPage() {
  return (
    <RequireAuth>
      <SensorsContent />
    </RequireAuth>
  );
}
