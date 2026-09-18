"use client";

/**
 * The GIS layer: forest zone boundaries and observation markers over
 * OpenStreetMap tiles. Markers are colour-coded by verification status, and
 * every popup that shows a coordinate also shows whether it was generalised
 * — the map must never imply more location precision than the API actually
 * returned.
 */

import "leaflet/dist/leaflet.css";

import L from "leaflet";
import { useEffect, useMemo } from "react";
import { Circle, CircleMarker, MapContainer, Popup, TileLayer, useMap } from "react-leaflet";

import { DEFAULT_MAP_CENTER, DEFAULT_MAP_ZOOM, MAP_ATTRIBUTION, MAP_TILE_URL } from "@/lib/config";
import { formatDateTime } from "@/lib/format";
import type { GeoJSONFeatureCollection, ZoneWithStats } from "@/lib/types";

// Leaflet's default marker icons reference image files that Next's bundler
// does not resolve automatically; CircleMarker is used everywhere instead,
// which sidesteps the icon problem entirely and lets colour carry meaning.
void L;

const STATUS_COLOR: Record<string, string> = {
  PENDING: "#f2b544",
  CONFIRMED: "#3f9670",
  CORRECTED: "#56b6c2",
  REJECTED: "#e5484d",
  UNCERTAIN: "#7a5330",
};

function FitToZones({ zones }: { zones: ZoneWithStats[] }) {
  const map = useMap();
  useEffect(() => {
    if (zones.length === 0) return;
    const bounds = L.latLngBounds(zones.map((zone) => [zone.center_latitude, zone.center_longitude]));
    map.fitBounds(bounds.pad(0.3));
  }, [zones, map]);
  return null;
}

interface BiodiversityMapProps {
  zones: ZoneWithStats[];
  observations: GeoJSONFeatureCollection | null;
  selectedZoneId: number | null;
}

export function BiodiversityMap({ zones, observations, selectedZoneId }: BiodiversityMapProps) {
  const filteredFeatures = useMemo(() => {
    if (!observations) return [];
    if (!selectedZoneId) return observations.features;
    return observations.features.filter((feature) => feature.properties.zone_id === selectedZoneId);
  }, [observations, selectedZoneId]);

  return (
    <MapContainer
      center={DEFAULT_MAP_CENTER}
      zoom={DEFAULT_MAP_ZOOM}
      scrollWheelZoom
      className="h-full w-full"
    >
      <TileLayer url={MAP_TILE_URL} attribution={MAP_ATTRIBUTION} />
      <FitToZones zones={zones} />

      {zones.map((zone) => (
        <Circle
          key={zone.id}
          center={[zone.center_latitude, zone.center_longitude]}
          radius={zone.radius_km * 1000}
          pathOptions={{
            color: "#3f9670",
            weight: selectedZoneId === zone.id ? 3 : 1.5,
            fillOpacity: 0.06,
          }}
        >
          <Popup>
            <div className="text-xs">
              <p className="font-semibold">{zone.name}</p>
              <p className="text-canopy-600">{zone.code} · {zone.habitat_type ?? "—"}</p>
              <p className="mt-1">
                {zone.observation_count} observations · {zone.species_count} species
              </p>
            </div>
          </Popup>
        </Circle>
      ))}

      {filteredFeatures.map((feature) => {
        const [lon, lat] = feature.geometry.coordinates;
        const status = String(feature.properties.verification_status ?? "PENDING");
        return (
          <CircleMarker
            key={String(feature.properties.id)}
            center={[lat as number, lon as number]}
            radius={6}
            pathOptions={{
              color: STATUS_COLOR[status] ?? "#a1d9bc",
              fillColor: STATUS_COLOR[status] ?? "#a1d9bc",
              fillOpacity: 0.85,
              weight: 1.5,
            }}
          >
            <Popup>
              <div className="min-w-40 text-xs">
                <p className="font-semibold">
                  {String(feature.properties.species ?? feature.properties.ai_prediction ?? "Unidentified")}
                </p>
                {feature.properties.scientific_name ? (
                  <p className="italic text-canopy-600">{String(feature.properties.scientific_name)}</p>
                ) : null}
                <p className="mt-1">{status}</p>
                <p className="text-canopy-500">
                  {formatDateTime(String(feature.properties.observed_at ?? ""))}
                </p>
                {feature.properties.location_generalised ? (
                  <p className="mt-1 text-amber-600">Location generalised for this taxon</p>
                ) : null}
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}

