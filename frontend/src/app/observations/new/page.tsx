"use client";

import { useRouter } from "next/navigation";
import { useState, type ChangeEvent, type FormEvent } from "react";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { RequireCapability } from "@/components/layout/RequireAuth";
import { InlineAlert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Field, Input, Label, Select, Textarea } from "@/components/ui/Field";
import { ApiError } from "@/lib/api";
import { observationsApi, speciesApi } from "@/lib/endpoints";
import { useOfflineStore } from "@/lib/offline-store";
import { useAsync } from "@/hooks/useAsync";

function nowLocalDatetime(): string {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 16);
}

function NewObservationContent() {
  const router = useRouter();
  const species = useAsync(() => speciesApi.list({ limit: 200 }), []);
  const isOnline = useOfflineStore((state) => state.isOnline);
  const queueObservation = useOfflineStore((state) => state.queueObservation);

  const [speciesId, setSpeciesId] = useState<string>("");
  const [observedAt, setObservedAt] = useState(nowLocalDatetime());
  const [latitude, setLatitude] = useState<string>("");
  const [longitude, setLongitude] = useState<string>("");
  const [locationAccuracy, setLocationAccuracy] = useState<string>("");
  const [notes, setNotes] = useState("");
  const [individualCount, setIndividualCount] = useState<string>("");
  const [image, setImage] = useState<File | null>(null);
  const [audio, setAudio] = useState<File | null>(null);
  const [locating, setLocating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [queued, setQueued] = useState(false);
  // Bumped on reset to remount the (uncontrolled) file inputs, since setting
  // their backing state to null does not clear what the native input shows.
  const [formKey, setFormKey] = useState(0);

  function handleFile(setter: (file: File | null) => void) {
    return (event: ChangeEvent<HTMLInputElement>) => setter(event.target.files?.[0] ?? null);
  }

  function useMyLocation() {
    if (!navigator.geolocation) {
      setError("Geolocation is not available in this browser.");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLatitude(position.coords.latitude.toFixed(6));
        setLongitude(position.coords.longitude.toFixed(6));
        setLocationAccuracy(String(Math.round(position.coords.accuracy)));
        setLocating(false);
      },
      () => {
        setError("Could not retrieve your location. Enter coordinates manually.");
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setQueued(false);

    const fields: Record<string, string> = {
      observed_at: new Date(observedAt).toISOString(),
    };
    if (speciesId) fields.species_id = speciesId;
    if (latitude) fields.latitude = latitude;
    if (longitude) fields.longitude = longitude;
    if (locationAccuracy) fields.location_accuracy_m = locationAccuracy;
    if (notes) fields.notes = notes;
    if (individualCount) fields.individual_count = individualCount;

    // A known-offline device skips straight to queueing — no point waiting on
    // a fetch that cannot succeed.
    if (!isOnline) {
      await queueObservation(fields, image, audio);
      setQueued(true);
      setSubmitting(false);
      resetForm();
      return;
    }

    try {
      const form = new FormData();
      for (const [key, value] of Object.entries(fields)) form.set(key, value);
      if (image) form.set("image", image);
      if (audio) form.set("audio", audio);

      const created = await observationsApi.capture(form);
      router.push(`/observations/${created.id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        // fetch() itself threw rather than resolving with a response — the
        // connection dropped mid-submission. Save it locally instead of
        // discarding a field researcher's capture.
        await queueObservation(fields, image, audio);
        setQueued(true);
        resetForm();
      }
    } finally {
      setSubmitting(false);
    }
  }

  function resetForm() {
    setSpeciesId("");
    setObservedAt(nowLocalDatetime());
    setLatitude("");
    setLongitude("");
    setLocationAccuracy("");
    setNotes("");
    setIndividualCount("");
    setImage(null);
    setAudio(null);
    setFormKey((value) => value + 1);
  }

  return (
    <AppShell title="New observation">
      <Card className="mx-auto max-w-2xl">
        <CardHeader
          title="Record a field observation"
          subtitle="Upload a photo, a recording, or both — AI-assisted identification runs automatically. The species you report stays yours until an expert reviews it."
        />
        <form className="space-y-5" onSubmit={handleSubmit} key={formKey}>
          {!isOnline ? (
            <InlineAlert tone="info">
              You&apos;re offline. Observations save on this device and upload automatically once
              you&apos;re back online.
            </InlineAlert>
          ) : null}
          {queued ? (
            <InlineAlert tone="info">
              Saved on this device — it will upload automatically once you&apos;re back online.
            </InlineAlert>
          ) : null}
          {error ? <InlineAlert tone="error">{error}</InlineAlert> : null}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field>
              <Label htmlFor="image">Photograph</Label>
              <Input id="image" type="file" accept="image/jpeg,image/png,image/webp" onChange={handleFile(setImage)} />
              {image ? <p className="mt-1 truncate text-xs text-canopy-400">{image.name}</p> : null}
            </Field>
            <Field>
              <Label htmlFor="audio">Recording</Label>
              <Input id="audio" type="file" accept="audio/wav,audio/flac,audio/ogg,audio/mpeg" onChange={handleFile(setAudio)} />
              {audio ? <p className="mt-1 truncate text-xs text-canopy-400">{audio.name}</p> : null}
            </Field>
          </div>

          <Field>
            <Label htmlFor="species">Species you observed (optional — AI will also suggest one)</Label>
            <Select id="species" value={speciesId} onChange={(event) => setSpeciesId(event.target.value)}>
              <option value="">— Not reporting a species —</option>
              {(species.data?.items ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.common_name} ({item.scientific_name})
                </option>
              ))}
            </Select>
          </Field>

          <Field>
            <Label htmlFor="observed_at">Date &amp; time observed</Label>
            <Input
              id="observed_at"
              type="datetime-local"
              required
              value={observedAt}
              onChange={(event) => setObservedAt(event.target.value)}
            />
          </Field>

          <div>
            <div className="mb-1 flex items-center justify-between">
              <Label htmlFor="latitude" className="mb-0">
                Location
              </Label>
              <button
                type="button"
                onClick={useMyLocation}
                disabled={locating}
                className="text-xs font-medium text-amber-glow-soft hover:underline disabled:opacity-50"
              >
                📍 {locating ? "Locating…" : "Use my location"}
              </button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Input
                id="latitude"
                placeholder="Latitude"
                value={latitude}
                onChange={(event) => setLatitude(event.target.value)}
              />
              <Input
                placeholder="Longitude"
                value={longitude}
                onChange={(event) => setLongitude(event.target.value)}
              />
            </div>
            {locationAccuracy ? (
              <p className="mt-1 text-xs text-canopy-400">±{locationAccuracy}m accuracy</p>
            ) : null}
          </div>

          <Field>
            <Label htmlFor="individual_count">Individuals observed (optional)</Label>
            <Input
              id="individual_count"
              type="number"
              min={0}
              value={individualCount}
              onChange={(event) => setIndividualCount(event.target.value)}
            />
          </Field>

          <Field>
            <Label htmlFor="notes">Field notes (optional)</Label>
            <Textarea
              id="notes"
              rows={3}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="Behaviour, habitat, weather…"
            />
          </Field>

          <Button type="submit" className="w-full" loading={submitting}>
            Save observation
          </Button>
        </form>
      </Card>
    </AppShell>
  );
}

export default function NewObservationPage() {
  return (
    <RequireAuth>
      <RequireCapability capability="can_record_observations">
        <NewObservationContent />
      </RequireCapability>
    </RequireAuth>
  );
}
