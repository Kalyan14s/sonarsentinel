/* Generated from backend/sonarsentinel/report/schema/report-1.0.schema.json by npm run gen:types. Do not edit. */

export type Utc = string;
export type UtcOrNull = Utc | null;
export type Detection = {
  [k: string]: unknown;
} & {
  detection_id: string;
  class: Class;
  confidence: number;
  alert_tier: Tier;
  position: {
    lat: Lat | null;
    lon: Lon | null;
    depth_m: number | null;
    uncertainty_m: NonNegativeOrNull;
  };
  /**
   * 4 × [lat, lon], clockwise; null when NOT_GEOTAGGED
   */
  footprint: [never[], never[], never[], never[]] | null;
  dimensions: {
    length_m: NonNegativeOrNull;
    width_m: NonNegativeOrNull;
    area_m2: NonNegativeOrNull;
    height_m: NonNegativeOrNull;
  };
  orientation_deg: number | null;
  sonar_ref: {
    source_file: string;
    side: "port" | "starboard" | "n/a";
    ping_start?: number | null;
    ping_end?: number | null;
    ground_range_m?: NonNegativeOrNull;
    time_utc?: UtcOrNull;
    /**
     * @minItems 4
     * @maxItems 4
     */
    pixel_bbox?: [number, number, number, number];
  };
  scores: {
    detector: Score;
    anomaly?: Score;
    shadow?: Score;
    fp_filter?: Score;
    persistence?: Score;
    dropout_penalty?: Score;
    motion_penalty?: Score;
    fused: Score;
  };
  quality_flags: QualityFlag[];
  n_views: number;
  review: {
    status: "pending" | "confirmed" | "rejected" | "reclassified";
    reviewer?: string | null;
    reject_reason?: "rock" | "shadow" | "ripples" | "noise" | "other" | null;
    note?: string | null;
    updated_utc?: UtcOrNull;
  };
  model_version: string;
  chip_url?: string | null;
};
export type Class = "shipwreck" | "pipe" | "cylinder" | "ghost_net" | "debris_other" | "unknown_anomaly";
export type Tier = "hazard" | "review" | "anomaly" | "hidden";
export type Lat = number;
export type Lon = number;
export type NonNegativeOrNull = number | null;
export type Score = number;
export type QualityFlag =
  | "DROPOUT"
  | "HIGH_MOTION"
  | "NEAR_NADIR"
  | "SURFACE_RETURN_BAND"
  | "TILE_EDGE"
  | "GPS_INTERPOLATED"
  | "LAYBACK_ESTIMATED"
  | "HEADING_FROM_COG"
  | "NO_ALTITUDE_BOTTOM_TRACKED"
  | "NOT_GEOTAGGED";

/**
 * Contract frozen at Gate G1. Human-readable field rules: docs/architecture/06-data-models.md.
 */
export interface SonarSentinelDetectionReport10 {
  report_version: "1.0";
  generated_utc: Utc;
  survey: {
    survey_id: string;
    name: string;
    project?: string | null;
    /**
     * @minItems 1
     */
    source_files: [string, ...string[]];
    source_format: "xtf" | "jsf" | "sl2" | "sl3" | "geotiff" | "image_nav" | "image_only";
    sonar?: {
      make?: string | null;
      model?: string | null;
      frequency_khz?: number | null;
      range_m?: number | null;
    } | null;
    start_utc?: UtcOrNull;
    end_utc?: UtcOrNull;
    track_length_km?: number | null;
    area_covered_km2?: number | null;
    datum: "WGS84";
    ground_resolution_m?: number | null;
    /**
     * [min_lon, min_lat, max_lon, max_lat]; null when NOT_GEOTAGGED
     */
    bbox: never[] | null;
  };
  processing: {
    pipeline_version: string;
    models: {
      [k: string]: string | null;
    };
    config_hash: string;
    runtime?: string | null;
    duration_s?: number | null;
    quality: {
      dropout_pings?: number;
      high_motion_pings?: number;
      bottom_tracked?: boolean;
      layback_estimated?: boolean;
      warnings: string[];
    };
  };
  summary: {
    total_detections: number;
    by_class: {
      [k: string]: number;
    };
    by_tier: {
      [k: string]: number;
    };
  };
  detections: Detection[];
}
