/**
 * S-01 upload screen logic (ST-091), kept free of React so it can be unit-tested:
 * client-side file checks, badges, start rules, options mapping, nav CSV template and
 * remembered advanced options (docs/wireframes/01-upload.md, API spec §2.1–2.2).
 */
import type { SurveyOptions, ValidatedFile } from '../api/client';

export const MAX_UPLOAD_BYTES = 2 * 1024 ** 3;
export const SUPPORTED_EXTENSIONS: readonly string[] = ['.xtf', '.tif', '.tiff', '.png', '.jpg', '.jpeg'];
export const ACCEPT = [...SUPPORTED_EXTENSIONS, '.csv'].join(',');
export const SUPPORTED_HINT = '.xtf, .tif, .png, .jpg';

export type RowStatus = 'validating' | 'done' | 'error' | 'offline';

export interface FileRow {
  id: number;
  file: File;
  status: RowStatus;
  result?: ValidatedFile;
  error?: string;
  errorCode?: string;
}

export interface Badge {
  kind: 'ok' | 'warn' | 'error';
  label: string;
}

export function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot > 0 ? name.slice(dot).toLowerCase() : '';
}

export function isNavCsv(name: string): boolean {
  return extensionOf(name) === '.csv';
}

export function formatBytes(bytes: number): string {
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  if (unit === 0) return `${Math.round(value)} B`;
  return `${value >= 100 ? value.toFixed(0) : value.toFixed(1)} ${units[unit]}`;
}

/** Problems found before calling the API: unsupported extension or over the size limit. */
export function localFileProblem(file: { name: string; size: number }): { code: string; message: string } | null {
  const ext = extensionOf(file.name);
  if (!SUPPORTED_EXTENSIONS.includes(ext)) {
    const what = ext || `"${file.name}" (no extension)`;
    return { code: 'UNSUPPORTED_FORMAT', message: `${what} is not supported — use ${SUPPORTED_HINT}` };
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return {
      code: 'FILE_TOO_LARGE',
      message: `${formatBytes(file.size)} exceeds the 2 GB limit (change in Settings)`,
    };
  }
  return null;
}

export function hasCrsWarning(result: ValidatedFile | undefined): boolean {
  return Boolean(result?.warnings.some((w) => w.startsWith('CRS_REQUIRED')));
}

export function badgeFor(row: FileRow): Badge | null {
  if (row.status === 'validating' || row.status === 'offline') return null;
  if (row.status === 'error') {
    if (row.errorCode === 'FILE_TOO_LARGE') return { kind: 'error', label: 'Too large' };
    if (row.errorCode === 'CORRUPT_HEADER') return { kind: 'error', label: 'Unreadable' };
    return { kind: 'error', label: 'Unsupported' };
  }
  const result = row.result;
  if (!result) return null;
  if (!result.valid) return { kind: 'error', label: 'Unsupported' };
  if (hasCrsWarning(result)) return { kind: 'warn', label: 'CRS needed' };
  if (result.format === 'geotiff') return { kind: 'ok', label: 'Georef' };
  if (result.has_navigation) return { kind: 'ok', label: 'GPS found' };
  return { kind: 'warn', label: 'No GPS' };
}

export function describeFile(result: ValidatedFile): string {
  const parts: string[] = [];
  if (result.format === 'xtf') {
    parts.push('XTF');
    const sonar = [result.sonar?.make, result.sonar?.model].filter(Boolean).join(' ');
    if (sonar) parts.push(sonar);
    if (result.sonar?.channels) parts.push(`${result.sonar.channels} ch`);
    if (result.pings !== undefined && result.pings !== null) parts.push(`${result.pings.toLocaleString('en-US')} pings`);
  } else if (result.format === 'geotiff') {
    parts.push('GeoTIFF');
    if (result.crs) parts.push(result.crs);
    if (result.resolution_m) parts.push(`${result.resolution_m} m/px`);
  } else {
    parts.push('Image');
    if (result.width && result.height) parts.push(`${result.width} × ${result.height} px`);
  }
  return parts.join(' · ');
}

export function isValidRow(row: FileRow): boolean {
  return row.status === 'done' && Boolean(row.result?.valid);
}

/** Valid file without navigation that needs a nav CSV or an explicit "Continue without GPS". */
export function needsNavigation(result: ValidatedFile | undefined): boolean {
  return Boolean(result && result.valid && !result.has_navigation && result.format !== 'geotiff');
}

/** Reasons Start analysis is disabled, most important first (empty = ready). */
export function startBlockers(
  rows: FileRow[],
  navAccepted: boolean,
  allowNoGps: boolean,
  epsgMissing: boolean,
): string[] {
  const reasons: string[] = [];
  const valid = rows.filter(isValidRow);
  if (rows.some((r) => r.status === 'validating')) reasons.push('Waiting for file checks to finish.');
  if (valid.length === 0) reasons.push('Add at least one supported sonar file.');
  if (valid.some((r) => needsNavigation(r.result)) && !navAccepted && !allowNoGps) {
    reasons.push('Attach a navigation CSV or choose Continue without GPS.');
  }
  if (epsgMissing) reasons.push('Choose a UTM zone (EPSG code) for projected coordinates.');
  return reasons;
}

/** Upload fraction of file `index` given bytes sent so far (files are sent in order). */
export function fileProgress(loaded: number, sizes: number[], index: number): number {
  const offset = sizes.slice(0, index).reduce((sum, size) => sum + size, 0);
  const size = sizes[index] ?? 0;
  if (size <= 0) return loaded > offset ? 1 : 0;
  return Math.min(Math.max((loaded - offset) / size, 0), 1);
}

// --- navigation CSV ------------------------------------------------------------------------

/** Columns read by backend/sonarsentinel/ingest/image_nav_reader.py (required + optional). */
export const NAV_TEMPLATE_COLUMNS = [
  'ping',
  'time_utc',
  'lat',
  'lon',
  'heading_deg',
  'slant_range_m',
  'altitude_m',
  'sensor_depth_m',
  'speed_mps',
  'roll_deg',
  'pitch_deg',
] as const;

export function navTemplateCsv(): string {
  return (
    `${NAV_TEMPLATE_COLUMNS.join(',')}\n` +
    '0,2026-09-12T05:10:02.00Z,13.084120,80.312750,62.4,50.0,8.0,10.2,1.0,0.0,0.0\n' +
    '100,2026-09-12T05:10:12.00Z,13.084510,80.313480,62.6,50.0,8.1,10.2,1.0,0.0,0.0\n'
  );
}

/** Required columns missing from a header (`ping`, `slant_range_m`, and lat/lon or easting/northing). */
export function missingNavColumns(header: string[]): string[] {
  const stripBom = (c: string) => (c.charCodeAt(0) === 0xfeff ? c.slice(1) : c);
  const cols = new Set(header.map((c) => stripBom(c).trim().replace(/^"|"$/g, '')));
  const missing = ['ping', 'slant_range_m'].filter((c) => !cols.has(c));
  const hasLatLon = cols.has('lat') && cols.has('lon');
  const hasUtm = cols.has('easting') && cols.has('northing');
  if (!hasLatLon && !hasUtm) missing.push(...['lat', 'lon'].filter((c) => !cols.has(c)));
  return missing;
}

async function readText(blob: Blob): Promise<string> {
  if (typeof blob.text === 'function') return blob.text();
  return new Response(blob).text();
}

export async function checkNavHeader(file: Blob): Promise<string[]> {
  try {
    const text = await readText(file.slice(0, 64 * 1024));
    const first = text.split(/\r?\n/, 1)[0] ?? '';
    return missingNavColumns(first.split(','));
  } catch {
    return [];
  }
}

// --- advanced options ----------------------------------------------------------------------

export interface AdvancedOptions {
  name: string;
  project: string;
  coordinates: 'auto' | 'utm';
  utmEpsg: string;
  groundResolution: number;
  layback: 'auto' | 'off' | 'manual';
  manualLaybackM: number | null;
  detectorModel: string;
  anomalyScan: boolean;
  /** Client-side display filter for the live map (no API field). */
  minShownPercent: number;
}

export const DEFAULT_OPTIONS: AdvancedOptions = {
  name: '',
  project: '',
  coordinates: 'auto',
  utmEpsg: '',
  groundResolution: 0.1,
  layback: 'auto',
  manualLaybackM: null,
  detectorModel: '',
  anomalyScan: true,
  minShownPercent: 30,
};

export function validEpsg(options: AdvancedOptions): boolean {
  return options.coordinates === 'utm' && /^\d{4,5}$/.test(options.utmEpsg.trim());
}

export function toSurveyOptions(options: AdvancedOptions, allowNoGps: boolean): SurveyOptions {
  const epsg = Number.parseInt(options.utmEpsg, 10);
  return {
    ...(options.name.trim() ? { name: options.name.trim() } : {}),
    ...(options.project.trim() ? { project: options.project.trim() } : {}),
    utm_epsg: validEpsg(options) && Number.isFinite(epsg) ? epsg : 'auto',
    ground_resolution_m: options.groundResolution,
    apply_layback: options.layback === 'auto' ? 'auto' : options.layback === 'off' ? 'false' : 'true',
    manual_layback_m:
      options.layback === 'manual' && Number.isFinite(options.manualLaybackM) ? options.manualLaybackM : null,
    anomaly_scan: options.anomalyScan,
    image_layout: 'port_stbd',
    allow_no_gps: allowNoGps,
    ...(options.detectorModel ? { detector_model: options.detectorModel } : {}),
  };
}

const OPTIONS_KEY = 'sonarsentinel.upload.options';
const OPEN_KEY = 'sonarsentinel.upload.advancedOpen';

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** Remembered options; the survey name is per survey and is not remembered. */
export function loadOptions(): AdvancedOptions {
  try {
    const raw = storage()?.getItem(OPTIONS_KEY);
    if (!raw) return { ...DEFAULT_OPTIONS };
    const parsed = JSON.parse(raw) as Partial<AdvancedOptions>;
    return { ...DEFAULT_OPTIONS, ...parsed, name: '' };
  } catch {
    return { ...DEFAULT_OPTIONS };
  }
}

export function saveOptions(options: AdvancedOptions): void {
  try {
    storage()?.setItem(OPTIONS_KEY, JSON.stringify({ ...options, name: '' }));
  } catch {
    // storage unavailable (private mode, blocked): options just aren't remembered
  }
}

export function loadAdvancedOpen(): boolean {
  try {
    return storage()?.getItem(OPEN_KEY) === 'true';
  } catch {
    return false;
  }
}

export function saveAdvancedOpen(open: boolean): void {
  try {
    storage()?.setItem(OPEN_KEY, String(open));
  } catch {
    // ignore
  }
}
