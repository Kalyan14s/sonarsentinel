import type { EditableSettings, Settings, SystemSettings } from '../api/client';

/** S-07 settings rules (ST-098, docs/wireframes/07-history-settings.md Part B). */
export const RUNTIME_OPTIONS = [
  { value: 'auto', label: 'Auto' },
  { value: 'torch', label: 'PyTorch' },
  { value: 'onnxruntime', label: 'ONNX Runtime (CPU)' },
  { value: 'cuda', label: 'PyTorch GPU (CUDA)' },
  { value: 'tensorrt', label: 'TensorRT' },
] as const;

export type SettingsErrors = Record<string, string>;

export function editableOf(settings: Settings): EditableSettings {
  const { detection, anomaly, tiers, map, processing, geo } = settings;
  return { detection, anomaly, tiers, map, processing, geo };
}

export function isDirty(a: EditableSettings | null, b: EditableSettings | null): boolean {
  return JSON.stringify(a) !== JSON.stringify(b);
}

const between = (value: number, low: number, high: number) => Number.isFinite(value) && value >= low && value <= high;

/** Client-side checks mirroring the server: tier order, ranges, offline tiles present. */
export function validateSettings(s: EditableSettings, system?: SystemSettings | null): SettingsErrors {
  const errors: SettingsErrors = {};
  const { hazard, review, anomaly } = s.tiers;
  if (![hazard, review, anomaly].every((v) => between(v, 0, 100))) {
    errors.tiers = 'Tier thresholds must be between 0 and 100';
  } else if (!(hazard > review && review > anomaly)) {
    errors.tiers = 'Hazard must be higher than Review, and Review higher than Anomaly';
  }
  if (!between(s.anomaly.threshold, 0, 1)) errors['anomaly.threshold'] = 'Anomaly threshold must be between 0 and 1';
  if (!between(s.detection.min_raw_score, 0, 1)) errors['detection.min_raw_score'] = 'Min. raw score must be between 0 and 1';
  if (!between(s.map.min_conf_default, 0, 100)) errors['map.min_conf_default'] = 'Map filter must be between 0 and 100';
  if (!(s.processing.ground_resolution_m > 0)) errors['processing.ground_resolution_m'] = 'Resolution must be above 0';
  if (!(Number.isInteger(s.processing.pings_per_chunk) && s.processing.pings_per_chunk > 0)) {
    errors['processing.pings_per_chunk'] = 'Chunk size must be a positive whole number';
  } else if (!(s.processing.overlap_pings >= 0 && s.processing.overlap_pings < s.processing.pings_per_chunk)) {
    errors['processing.overlap_pings'] = 'Overlap must be at least 0 and smaller than the chunk size';
  }
  if (!(s.geo.cluster_radius_m >= 0)) errors['geo.cluster_radius_m'] = 'Cluster radius must be 0 or more';
  if (s.map.basemap === 'offline' && system && !system.offline_tiles_available) {
    errors['map.basemap'] = 'No offline tiles installed (tiles/basemap.mbtiles)';
  }
  return errors;
}

/** Server `VALIDATION_ERROR` details → field messages (object of field → message, or an `errors` list). */
export function serverErrors(message: string, details: Record<string, unknown>): SettingsErrors {
  const out: SettingsErrors = {};
  const list = details.errors;
  if (Array.isArray(list)) {
    for (const entry of list) {
      const field = (entry as { field?: unknown }).field;
      const text = (entry as { message?: unknown }).message;
      if (typeof field === 'string') out[field] = typeof text === 'string' ? text : message;
    }
  }
  if (typeof details.field === 'string') out[details.field] = message;
  for (const [key, value] of Object.entries(details)) {
    if (key !== 'errors' && key !== 'field' && typeof value === 'string') out[key] = value;
  }
  if (Object.keys(out).length === 0) out.form = message;
  return out;
}
