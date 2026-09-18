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
import { useAsync } from "@/hooks/useAsync";

function nowLocalDatetime(): string {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 16);
}

function NewObservationContent() {
  const router = useRouter();
  const species = useAsync(() => speciesApi.list({ limit: 200 }), []);

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
    try {
      const form = new FormData();
      form.set("observed_at", new Date(observedAt).toISOString());
      if (speciesId) form.set("species_id", speciesId);
      if (latitude) form.set("latitude", latitude);
      if (longitude) form.set("longitude", longitude);
      if (locationAccuracy) form.set("location_accuracy_m", locationAccuracy);
      if (notes) form.set("notes", notes);
      if (individualCount) form.set("individual_count", individualCount);
      if (image) form.set("image", image);
      if (audio) form.set("audio", audio);

      const created = await observationsApi.capture(form);
      router.push(`/observations/${created.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the observation.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AppShell title="New observation">
      <Card className="mx-auto max-w-2xl">
        <CardHeader
          title="Record a field observation"
          subtitle="Upload a photo, a recording, or both — AI-assisted identification runs automatically. The species you report stays yours until an expert reviews it."
        />
        <form className="space-y-5" onSubmit={handleSubmit}>
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
