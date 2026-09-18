/**
 * Typed calls grouped by backend module — mirrors backend/app/api/v1/*.py
 * one file to one namespace here, so finding "the call that hits
 * POST /observations/capture" is a matter of opening observations.ts.
 */

import { api } from "./api";
import type {
  AIEngineStatus,
  AIPerformanceReport,
  AlertRead,
  AlertStatus,
  DetectionTrend,
  DeviceHealth,
  DeviceRead,
  DiversityIndices,
  ExperimentReport,
  ExperimentRead,
  GeoJSONFeatureCollection,
  GeographicDistribution,
  LoginRequestBody,
  MeResponse,
  ObservationDetail,
  ObservationRead,
  OverviewCounts,
  Page,
  PredictionResult,
  RegisterRequestBody,
  ReviewQueueItem,
  SeasonalPattern,
  SpeciesFrequency,
  SpeciesRead,
  SpeciesWithStats,
  TokenPair,
  UserPublic,
  VerificationRead,
  VerificationStats,
  ZoneComparison,
  ZoneWithStats,
} from "./types";

// --------------------------------------------------------------------------
// auth
// --------------------------------------------------------------------------
export const authApi = {
  register: (body: RegisterRequestBody) =>
    api.post<UserPublic>("/auth/register", body, { auth: false }),
  login: (body: LoginRequestBody) =>
    api.post<TokenPair>("/auth/login", body, { auth: false, skipRefreshOn401: true }),
  me: () => api.get<MeResponse>("/auth/me"),
  logout: (refresh_token?: string) => api.post("/auth/logout", { refresh_token }),
  changePassword: (current_password: string, new_password: string) =>
    api.post("/auth/change-password", { current_password, new_password }),
};

// --------------------------------------------------------------------------
// species
// --------------------------------------------------------------------------
export const speciesApi = {
  list: (params?: {
    search?: string;
    category?: string;
    conservation_status?: string;
    threatened_only?: boolean;
    audible_only?: boolean;
    limit?: number;
    offset?: number;
  }) => api.get<Page<SpeciesRead>>("/species", params, { auth: false }),
  get: (id: number) => api.get<SpeciesWithStats>(`/species/${id}`, undefined, { auth: false }),
  categories: () => api.get<Record<string, number>>("/species/categories", undefined, {
    auth: false,
  }),
};

// --------------------------------------------------------------------------
// observations
// --------------------------------------------------------------------------
export const observationsApi = {
  list: (params?: Record<string, string | number | boolean | undefined>) =>
    api.get<Page<ObservationRead>>("/observations", params, { auth: false }),
  mine: (params?: Record<string, string | number | undefined>) =>
    api.get<Page<ObservationRead>>("/observations/me", params),
  get: (id: number) => api.get<ObservationDetail>(`/observations/${id}`, undefined, {
    auth: false,
  }),
  capture: (form: FormData) => api.postForm<ObservationDetail>("/observations/capture", form),
  summary: () => api.get<{ pending_review: number; pending_over_14_days: number }>(
    "/observations/stats/summary"
  ),
  reidentify: (id: number) => api.post<PredictionResult[]>(`/observations/${id}/identify`),
};

// --------------------------------------------------------------------------
// ai
// --------------------------------------------------------------------------
export const aiApi = {
  status: () => api.get<AIEngineStatus>("/ai/status", undefined, { auth: false }),
};

// --------------------------------------------------------------------------
// zones / gis
// --------------------------------------------------------------------------
export const zonesApi = {
  list: () => api.get<ZoneWithStats[]>("/zones", undefined, { auth: false }),
  zonesGeoJSON: () =>
    api.get<GeoJSONFeatureCollection>("/zones/geojson", undefined, { auth: false }),
  observationsGeoJSON: (params?: Record<string, string | number | undefined>) =>
    api.get<GeoJSONFeatureCollection>("/zones/observations/geojson", params, { auth: false }),
};

// --------------------------------------------------------------------------
// analytics
// --------------------------------------------------------------------------
export const analyticsApi = {
  overview: () => api.get<OverviewCounts>("/analytics/overview", undefined, { auth: false }),
  trends: (params?: Record<string, string | number | undefined>) =>
    api.get<DetectionTrend>("/analytics/trends", params, { auth: false }),
  speciesFrequency: (params?: Record<string, string | number | undefined>) =>
    api.get<SpeciesFrequency[]>("/analytics/species-frequency", params, { auth: false }),
  diversity: (params?: Record<string, string | number | undefined>) =>
    api.get<DiversityIndices>("/analytics/diversity", params, { auth: false }),
  zones: (params?: Record<string, string | undefined>) =>
    api.get<ZoneComparison[]>("/analytics/zones", params, { auth: false }),
  seasonal: (params?: Record<string, string | number | undefined>) =>
    api.get<SeasonalPattern>("/analytics/seasonal", params, { auth: false }),
  aiPerformance: () => api.get<AIPerformanceReport>("/analytics/ai-performance"),
  geographic: (params?: Record<string, string | number | undefined>) =>
    api.get<GeographicDistribution>("/analytics/geographic", params, { auth: false }),
  exportCsvUrl: (verifiedOnly = true) =>
    `/analytics/export.csv?verified_only=${verifiedOnly}`,
};

// --------------------------------------------------------------------------
// verification
// --------------------------------------------------------------------------
export const verificationApi = {
  queue: (params?: Record<string, string | number | boolean | undefined>) =>
    api.get<Page<ReviewQueueItem>>("/verifications/queue", params),
  stats: () => api.get<VerificationStats>("/verifications/stats"),
  submit: (
    observationId: number,
    decision: string,
    corrected_species_id?: number,
    comments?: string
  ) =>
    api.post<VerificationRead>(`/verifications/observation/${observationId}`, {
      decision,
      corrected_species_id,
      comments,
    }),
  history: (observationId: number) =>
    api.get<VerificationRead[]>(`/verifications/observation/${observationId}`),
};

// --------------------------------------------------------------------------
// alerts
// --------------------------------------------------------------------------
export const alertsApi = {
  list: (params?: { status?: AlertStatus; limit?: number; offset?: number }) =>
    api.get<Page<AlertRead>>("/alerts", params),
  get: (id: number) => api.get<AlertRead>(`/alerts/${id}`),
  update: (
    id: number,
    body: { status: AlertStatus; resolution_notes?: string; confirmed_cause?: string }
  ) => api.patch<AlertRead>(`/alerts/${id}`, body),
  detect: (zone_id?: number) =>
    api.post<{ evaluated_windows: number; anomalies_found: number; alerts_created: number }>(
      "/alerts/detect",
      { zone_id }
    ),
};

// --------------------------------------------------------------------------
// sensors / iot
// --------------------------------------------------------------------------
export const sensorsApi = {
  devices: (params?: { zone_id?: number }) =>
    api.get<DeviceRead[]>("/sensors/devices", params),
  health: () => api.get<DeviceHealth[]>("/sensors/devices/health"),
};

// --------------------------------------------------------------------------
// research
// --------------------------------------------------------------------------
export const researchApi = {
  variants: () =>
    api.get<{
      variants: Record<string, string>;
      datasets: Record<string, string>;
      verified_dataset: { verified_observations: number; verified_with_media: number;
        minimum_required: number };
    }>("/research/variants"),
  list: () => api.get<ExperimentRead[]>("/research"),
  create: (name: string, research_question: string, hypothesis?: string) =>
    api.post<ExperimentRead>("/research", { name, research_question, hypothesis }),
  run: (id: number, body: { variants?: string[]; sample_count?: number; dataset?: string }) =>
    api.post<ExperimentReport>(`/research/${id}/run`, body),
};

// --------------------------------------------------------------------------
// users (admin)
// --------------------------------------------------------------------------
export const usersApi = {
  list: (params?: Record<string, string | number | undefined>) =>
    api.get<Page<UserPublic>>("/users", params),
  create: (body: {
    full_name: string;
    email: string;
    password: string;
    role: string;
    organization?: string;
    expertise?: string;
  }) => api.post<UserPublic>("/users", body),
  update: (id: number, body: { role?: string; is_active?: boolean }) =>
    api.patch<UserPublic>(`/users/${id}`, body),
  deactivate: (id: number) => api.delete(`/users/${id}`),
};
