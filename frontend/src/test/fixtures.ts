import type { Detection, SurveySummary } from '../api/client';

const CLASSES = ['ghost_net', 'shipwreck', 'pipe', 'cylinder', 'debris_other', 'unknown_anomaly'] as const;

export function tierFor(confidence: number): Detection['alert_tier'] {
  if (confidence >= 80) return 'hazard';
  if (confidence >= 50) return 'review';
  if (confidence >= 30) return 'anomaly';
  return 'hidden';
}

/** A schema-shaped detection; `i` varies class, confidence, position and ping. */
export function makeDetection(i: number, overrides: Partial<Detection> = {}): Detection {
  const confidence = overrides.confidence ?? Math.round(((i * 37) % 100) * 10) / 10;
  return {
    detection_id: `SRV-20260913-001-D${String(i).padStart(4, '0')}`,
    class: CLASSES[i % CLASSES.length] as Detection['class'],
    confidence,
    alert_tier: tierFor(confidence),
    position: { lat: 13.08412 + i * 1e-5, lon: 80.31275 + i * 1e-5, depth_m: 18.5, uncertainty_m: 4.2 },
    footprint: null,
    dimensions: { length_m: 6.2, width_m: 3.1, area_m2: 14.8 + i, height_m: 0.4 },
    orientation_deg: 12,
    sonar_ref: {
      source_file: 'line_07.xtf',
      side: 'starboard',
      ping_start: 100 + i * 10,
      ping_end: 160 + i * 10,
      ground_range_m: 23.7,
      time_utc: '2026-09-12T05:17:21.50Z',
    },
    scores: {
      detector: 0.81,
      anomaly: 0.92,
      shadow: 0.64,
      fp_filter: 0.88,
      persistence: 0.5,
      dropout_penalty: 0,
      motion_penalty: 0,
      fused: 0.78,
    },
    quality_flags: [],
    n_views: 1,
    review: { status: 'pending', reviewer: null, reject_reason: null, note: null, updated_utc: null },
    model_version: 'yolo11s-seg-sonar-real@0.1.0',
    chip_url: null,
    ...overrides,
  };
}

export function makeDetections(n: number): Detection[] {
  return Array.from({ length: n }, (_, i) => makeDetection(i + 1));
}

export function makeSurvey(overrides: Partial<SurveySummary> = {}): SurveySummary {
  return {
    survey_id: 'SRV-20260913-001',
    name: 'Chennai-Port-Line07',
    created_utc: '2026-09-13T10:00:00Z',
    source_files: ['line_07.xtf'],
    job: { job_id: 'JOB-00000001', status: 'completed', duration_s: 48.6 },
    bbox: [80.3, 13.08, 80.32, 13.09],
    track_length_km: 1.2,
    summary: { total_detections: 0, by_class: {}, by_tier: {} },
    report_urls: {},
    ...overrides,
  };
}

export const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
