/**
 * TypeScript mirrors of the backend's Pydantic schemas (see
 * backend/app/schemas/). Kept intentionally close to the API's own field
 * names so a response can be used with no translation layer.
 */

export type UserRole = "ADMIN" | "RESEARCHER" | "FOREST_OFFICER" | "EXPERT" | "VIEWER";

export interface UserPublic {
  id: number;
  full_name: string;
  email: string;
  role: UserRole;
  organization: string | null;
  expertise: string | null;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface UserCapabilities {
  can_record_observations: boolean;
  can_verify: boolean;
  can_manage_species: boolean;
  can_manage_users: boolean;
  can_manage_alerts: boolean;
  can_run_experiments: boolean;
  can_see_precise_locations: boolean;
}

export interface MeResponse {
  user: UserPublic;
  capabilities: UserCapabilities;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  expires_at: string;
  user: UserPublic;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export type SpeciesCategory =
  | "MAMMAL"
  | "BIRD"
  | "PLANT"
  | "REPTILE"
  | "AMPHIBIAN"
  | "INSECT"
  | "FUNGI"
  | "OTHER";

export type ConservationStatus = "EX" | "EW" | "CR" | "EN" | "VU" | "NT" | "LC" | "DD" | "NE";

export interface SpeciesSummary {
  id: number;
  common_name: string;
  scientific_name: string;
  category: SpeciesCategory;
  conservation_status: ConservationStatus;
}

export interface SpeciesRead extends SpeciesSummary {
  family: string | null;
  genus: string | null;
  description: string | null;
  habitat: string | null;
  is_location_sensitive: boolean;
  image_url: string | null;
  reference_url: string | null;
  visual_traits: Record<string, unknown> | null;
  acoustic_signature: Record<string, unknown> | null;
  research_notes: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface SpeciesWithStats extends SpeciesRead {
  observation_count: number;
  verified_observation_count: number;
  last_observed_at: string | null;
}

export type ObservationType =
  | "IMAGE"
  | "AUDIO"
  | "MULTIMODAL"
  | "FIELD_NOTE"
  | "CAMERA_TRAP"
  | "SENSOR";

export type VerificationStatus = "PENDING" | "CONFIRMED" | "REJECTED" | "CORRECTED" | "UNCERTAIN";

export interface MediaAssetRead {
  id: number;
  kind: string;
  public_url: string;
  mime_type: string;
  size_bytes: number;
  checksum: string;
  width: number | null;
  height: number | null;
  duration_seconds: number | null;
  sample_rate: number | null;
  original_filename: string | null;
  created_at: string;
}

export interface PredictionCandidate {
  species_id: number | null;
  label: string;
  scientific_name: string | null;
  confidence: number;
}

export interface DetectionBox {
  bbox: [number, number, number, number];
  score: number;
  label: string | null;
}

export interface AIPredictionRead {
  id: number;
  observation_id: number | null;
  modality: "IMAGE" | "AUDIO" | "SENSOR" | "FUSED";
  model_name: string;
  model_version: string;
  predicted_label: string;
  predicted_species: SpeciesSummary | null;
  confidence: number;
  is_uncertain: boolean;
  requires_expert_verification: boolean;
  identification_basis: string;
  top_k: PredictionCandidate[] | null;
  detections: DetectionBox[] | null;
  diagnostics: Record<string, unknown> | null;
  latency_ms: number | null;
  created_at: string;
}

export interface ObservationRead {
  id: number;
  researcher_id: number;
  observation_type: ObservationType;
  species: SpeciesSummary | null;
  zone_id: number | null;
  zone_name: string | null;
  image_url: string | null;
  audio_url: string | null;
  latitude: number | null;
  longitude: number | null;
  location_accuracy_m: number | null;
  elevation_m: number | null;
  location_generalised: boolean;
  observed_at: string;
  notes: string | null;
  individual_count: number | null;
  conditions: Record<string, unknown> | null;
  ai_prediction: string | null;
  ai_confidence: number | null;
  ai_model_version: string | null;
  ai_predicted_species: SpeciesSummary | null;
  verification_status: VerificationStatus;
  verified_species: SpeciesSummary | null;
  verified_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ObservationDetail extends ObservationRead {
  researcher: UserPublic | null;
  media: MediaAssetRead[];
  predictions: AIPredictionRead[];
  final_species: SpeciesSummary | null;
}

export interface PredictionResult {
  modality: "IMAGE" | "AUDIO" | "SENSOR" | "FUSED";
  model_name: string;
  model_version: string;
  predicted_label: string;
  predicted_species: SpeciesSummary | null;
  confidence: number;
  is_uncertain: boolean;
  requires_expert_verification: boolean;
  identification_basis: string;
  top_k: PredictionCandidate[];
  detections: DetectionBox[];
  diagnostics: Record<string, unknown> | null;
  latency_ms: number | null;
}

export interface ZoneRead {
  id: number;
  name: string;
  code: string;
  description: string | null;
  habitat_type: string | null;
  area_hectares: number | null;
  center_latitude: number;
  center_longitude: number;
  radius_km: number;
  boundary_geojson: Record<string, unknown> | null;
  created_at: string;
}

export interface ZoneWithStats extends ZoneRead {
  observation_count: number;
  species_count: number;
  device_count: number;
  last_observed_at: string | null;
}

export interface GeoJSONFeature {
  type: "Feature";
  geometry: { type: string; coordinates: number[] };
  properties: Record<string, unknown>;
}

export interface GeoJSONFeatureCollection {
  type: "FeatureCollection";
  features: GeoJSONFeature[];
  location_generalised: boolean;
  total: number;
}

export interface OverviewCounts {
  species_total: number;
  species_observed: number;
  species_by_category: Record<string, number>;
  observations_total: number;
  observations_last_30_days: number;
  observations_verified: number;
  observations_pending: number;
  ai_predictions_total: number;
  ai_uncertain_share: number | null;
  zones_total: number;
  devices_active: number;
  open_alerts: number;
  new_species_this_month: number;
  disclaimer: string;
}

export interface TrendPoint {
  period: string;
  observations: number;
  distinct_species: number;
  verified: number;
}

export interface DetectionTrend {
  granularity: string;
  points: TrendPoint[];
  disclaimer: string;
}

export interface SpeciesFrequency {
  species_id: number;
  common_name: string;
  scientific_name: string;
  category: string;
  detections: number;
  share: number;
  verified_detections: number;
  last_detected_at: string | null;
}

export interface DiversityIndices {
  sample_count: number;
  species_richness: number;
  shannon_index: number | null;
  shannon_evenness: number | null;
  simpson_index: number | null;
  inverse_simpson: number | null;
  chao1_estimate: number | null;
  singletons: number;
  doubletons: number;
  comparable: boolean;
  caveat: string;
}

export interface ZoneComparison {
  zone_id: number;
  zone_code: string;
  zone_name: string;
  observations: number;
  species_richness: number;
  shannon_index: number | null;
  detections_per_active_day: number | null;
  open_alerts: number;
}

export interface SeasonalBucket {
  month: number;
  month_name: string;
  observations: number;
  distinct_species: number;
  dominant_category: string | null;
}

export interface SeasonalPattern {
  buckets: SeasonalBucket[];
  years_covered: number[];
  disclaimer: string;
}

export interface ConfidenceBin {
  lower: number;
  upper: number;
  count: number;
  expert_confirmed: number;
  expert_rejected: number;
}

export interface AIPerformanceReport {
  predictions_total: number;
  uncertain_total: number;
  mean_confidence: number | null;
  confidence_bins: ConfidenceBin[];
  reviewed_total: number;
  agreement_rate: number | null;
  false_positive_candidates: number;
  caveat: string;
}

export interface GeographicCell {
  latitude: number;
  longitude: number;
  observations: number;
  distinct_species: number;
  precision_deg: number;
}

export interface GeographicDistribution {
  cells: GeographicCell[];
  precision_deg: number;
  location_generalised: boolean;
  disclaimer: string;
}

export type VerificationDecision = "CONFIRM" | "REJECT" | "CORRECT" | "UNCERTAIN";

export interface ReviewQueueItem {
  observation: ObservationRead;
  ai_predicted_label: string | null;
  ai_confidence: number | null;
  reported_species: SpeciesSummary | null;
  waiting_days: number;
  has_image: boolean;
  has_audio: boolean;
}

export interface VerificationRead {
  id: number;
  observation_id: number;
  expert: UserPublic | null;
  decision: VerificationDecision;
  corrected_species: SpeciesSummary | null;
  previous_species: SpeciesSummary | null;
  ai_predicted_label: string | null;
  ai_confidence: number | null;
  comments: string | null;
  verified_at: string;
}

export interface AgreementCell {
  ai_label: string;
  expert_label: string;
  count: number;
}

export interface VerificationStats {
  reviewed_count: number;
  confirmed: number;
  rejected: number;
  corrected: number;
  uncertain: number;
  ai_agreement_rate: number | null;
  mean_confidence_when_agreed: number | null;
  mean_confidence_when_disagreed: number | null;
  top_confusions: AgreementCell[];
  note: string;
}

export type AlertKind =
  | "BIODIVERSITY_ANOMALY"
  | "ACOUSTIC_ANOMALY"
  | "SENSOR_MALFUNCTION"
  | "DEVICE_OFFLINE"
  | "DATA_GAP"
  | "THREATENED_SPECIES_DETECTION";

export type AlertSeverity = "INFO" | "LOW" | "MEDIUM" | "HIGH";
export type AlertStatus = "OPEN" | "INVESTIGATING" | "RESOLVED" | "DISMISSED";

export interface AlertRead {
  id: number;
  kind: AlertKind;
  severity: AlertSeverity;
  status: AlertStatus;
  zone_id: number | null;
  zone_name: string | null;
  device_id: number | null;
  title: string;
  message: string;
  evidence: Record<string, unknown> | null;
  candidate_causes: string[] | null;
  detected_at: string;
  acknowledged_at: string | null;
  acknowledged_by_id: number | null;
  resolved_at: string | null;
  resolution_notes: string | null;
  confirmed_cause: string | null;
  created_at: string;
}

export type DeviceKind = "CAMERA_TRAP" | "ACOUSTIC_RECORDER" | "ENV_SENSOR" | "MULTI_SENSOR_NODE";

export interface DeviceRead {
  id: number;
  device_code: string;
  name: string;
  kind: DeviceKind;
  zone_id: number | null;
  latitude: number | null;
  longitude: number | null;
  firmware_version: string | null;
  report_interval_minutes: number;
  is_active: boolean;
  last_seen_at: string | null;
  created_at: string;
}

export interface DeviceHealth {
  device_id: number;
  device_code: string;
  name: string;
  kind: string;
  zone_id: number | null;
  status: "online" | "late" | "offline" | "never_reported" | "disabled";
  last_seen_at: string | null;
  silent_minutes: number | null;
  report_interval_minutes: number;
  battery_volts: number | null;
  reading_count: number;
}

export interface ModelInfo {
  modality: string;
  name: string;
  version: string;
  backend: string;
  class_count: number;
  min_confidence: number;
  uncertain_margin: number;
  notes: string | null;
}

export interface AIEngineStatus {
  vision: ModelInfo;
  audio: ModelInfo;
  anomaly_methods: string[];
  fusion_available: boolean;
}

export interface ExperimentRunRead {
  id: number;
  variant: string;
  metrics: Record<string, number> | null;
  per_class_metrics: Record<string, unknown> | null;
  confusion_matrix: Record<string, unknown> | null;
  sample_count: number | null;
  random_seed: number | null;
  notes: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface ExperimentRead {
  id: number;
  name: string;
  research_question: string;
  hypothesis: string | null;
  status: "DRAFT" | "RUNNING" | "COMPLETED" | "FAILED";
  config: Record<string, unknown> | null;
  created_by_id: number | null;
  created_at: string;
  runs: ExperimentRunRead[];
}

export interface VariantComparison {
  variant: string;
  accuracy: number;
  macro_precision: number;
  macro_recall: number;
  macro_f1: number;
  mean_average_precision: number;
  expected_calibration_error: number;
  uncertain_share: number;
  mean_latency_ms: number;
}

export interface ExperimentReport {
  experiment_id: number;
  name: string;
  research_question: string;
  dataset: string;
  sample_count: number;
  random_seed: number;
  comparisons: VariantComparison[];
  best_variant: string;
  fusion_gain_f1: number;
  conclusion: string;
  caveat: string;
}

export interface ApiErrorBody {
  detail: string;
  fields?: Record<string, string>;
  context?: Record<string, unknown>;
}

export interface RegisterRequestBody {
  full_name: string;
  email: string;
  password: string;
  password_confirm?: string;
  organization?: string;
  role: "RESEARCHER" | "VIEWER";
}

export interface LoginRequestBody {
  email: string;
  password: string;
}
