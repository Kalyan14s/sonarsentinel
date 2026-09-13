/**
 * Typed client for the SonarSentinel API (docs/architecture/05-api-specification.md).
 * Report and detection types are generated from the backend JSON Schema (npm run gen:types).
 */
import type { SonarSentinelDetectionReport10 as Report } from './report-schema';

export type { Report };
export type Detection = Report['detections'][number];

export interface ApiErrorBody {
  error: { code: string; message: string; details: Record<string, unknown> };
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

export interface SurveySummary {
  survey_id: string;
  name: string;
  created_utc: string;
  source_files: string[];
  job: { job_id: string; status: string; duration_s: number | null };
  bbox: [number, number, number, number] | null;
  track_length_km: number | null;
  summary: Report['summary'];
}

export interface Paged<T> {
  total: number;
  items: T[];
}

export interface TrackGeoJson {
  type: 'FeatureCollection';
  features: { type: 'Feature'; geometry: { type: 'LineString'; coordinates: [number, number][] } }[];
}

export interface DetectionQuery {
  class?: string[];
  min_conf?: number;
  tier?: string[];
  sort?: 'confidence' | '-confidence' | 'area' | 'ping';
  limit?: number;
  offset?: number;
}

export interface ModelInfo {
  kind: string;
  id: string;
  available: boolean;
  trained: boolean;
}

/** One entry of `POST /surveys/validate` (API spec §2.2). */
export interface ValidatedFile {
  filename: string;
  valid: boolean;
  format: string;
  size_bytes?: number;
  sonar?: { make: string | null; model: string | null; channels: number | null } | null;
  pings?: number | null;
  has_navigation: boolean;
  nav_units?: string | null;
  start_utc?: string | null;
  end_utc?: string | null;
  width?: number;
  height?: number;
  crs?: string | null;
  resolution_m?: number | null;
  warnings: string[];
}

export interface ValidateResponse {
  files: ValidatedFile[];
}

/** `options` JSON of `POST /surveys` (API spec §2.1). */
export interface SurveyOptions {
  name?: string;
  project?: string;
  utm_epsg: 'auto' | number;
  ground_resolution_m: number;
  apply_layback: 'auto' | 'true' | 'false';
  manual_layback_m: number | null;
  anomaly_scan: boolean;
  image_layout: 'port_stbd' | 'port_only' | 'stbd_only';
  allow_no_gps: boolean;
  detector_model?: string;
}

export interface CreateSurveyResponse {
  survey_id: string;
  job_id: string;
  status: string;
  ws_url: string;
}

export interface UploadProgress {
  loaded: number;
  total: number;
}

export type JobEvent =
  | { type: 'progress'; seq: number; stage: string; percent: number; pings_done?: number; pings_total?: number }
  | { type: 'track'; seq: number; points: [number, number][]; ping_start: number; ping_end: number }
  | { type: 'detection'; seq: number; detection: Detection }
  | { type: 'warning'; seq: number; code: string; message: string; ping_start: number; ping_end: number }
  | { type: 'done'; seq: number; status: string; summary: Report['summary'] }
  | { type: 'error'; seq: number; code: string; message: string };

const API = '/api/v1';

function apiErrorFrom(status: number, body: unknown, fallback: string): ApiError {
  const error = (body as Partial<ApiErrorBody> | undefined)?.error;
  return new ApiError(
    status,
    error?.code ?? 'INTERNAL_ERROR',
    error?.message ?? (fallback || `HTTP ${status}`),
    error?.details ?? {},
  );
}

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return undefined;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, init);
  if (!response.ok) {
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = undefined;
    }
    throw apiErrorFrom(response.status, body, response.statusText);
  }
  return (await response.json()) as T;
}

export function detectionQueryString(query: DetectionQuery): string {
  const params = new URLSearchParams();
  if (query.class?.length) params.set('class', query.class.join(','));
  if (query.tier?.length) params.set('tier', query.tier.join(','));
  if (query.min_conf !== undefined) params.set('min_conf', String(query.min_conf));
  if (query.sort) params.set('sort', query.sort);
  if (query.limit !== undefined) params.set('limit', String(query.limit));
  if (query.offset !== undefined) params.set('offset', String(query.offset));
  const text = params.toString();
  return text ? `?${text}` : '';
}

/** Multipart form shared by validate and create: `files`, optional `nav_csv`, `options` JSON. */
export function surveyForm(files: File[], navCsv?: File | null, options?: SurveyOptions): FormData {
  const form = new FormData();
  for (const file of files) form.append('files', file, file.name);
  if (navCsv) form.append('nav_csv', navCsv, navCsv.name);
  if (options) form.append('options', JSON.stringify(options));
  return form;
}

export const api = {
  health: () => request<{ status: string; version: string; runtime: string }>('/health'),
  models: () => request<Paged<ModelInfo>>('/models'),
  surveys: () => request<Paged<SurveySummary>>('/surveys'),
  survey: (id: string) => request<SurveySummary>(`/surveys/${encodeURIComponent(id)}`),
  track: (id: string) => request<TrackGeoJson>(`/surveys/${encodeURIComponent(id)}/track`),
  detections: (id: string, query: DetectionQuery = {}) =>
    request<Paged<Detection>>(`/surveys/${encodeURIComponent(id)}/detections${detectionQueryString(query)}`),
  reportUrl: (id: string, format: 'json' | 'csv') =>
    `${API}/surveys/${encodeURIComponent(id)}/report?format=${format}`,
};

/**
 * `POST /surveys/validate`: header checks only, nothing is processed.
 * HTTP errors throw {@link ApiError}; a network failure throws the fetch `TypeError`.
 */
export function validateSurvey(
  files: File[],
  navCsv?: File | null,
  options?: SurveyOptions,
): Promise<ValidateResponse> {
  return request<ValidateResponse>('/surveys/validate', {
    method: 'POST',
    body: surveyForm(files, navCsv, options),
  });
}

/**
 * `POST /surveys` with upload progress (XMLHttpRequest, since fetch has no upload progress).
 * Rejects with {@link ApiError} (status 0 = backend not reachable) or an `AbortError` DOMException.
 */
export function createSurvey(
  files: File[],
  navCsv: File | null,
  options: SurveyOptions,
  handlers: { onProgress?: (progress: UploadProgress) => void; signal?: AbortSignal } = {},
): Promise<CreateSurveyResponse> {
  return new Promise((resolve, reject) => {
    const { onProgress, signal } = handlers;
    if (signal?.aborted) {
      reject(new DOMException('Upload cancelled', 'AbortError'));
      return;
    }
    const xhr = new XMLHttpRequest();
    const abort = () => xhr.abort();
    signal?.addEventListener('abort', abort, { once: true });
    const cleanup = () => signal?.removeEventListener('abort', abort);

    xhr.open('POST', `${API}/surveys`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.({ loaded: event.loaded, total: event.total });
    };
    xhr.onload = () => {
      cleanup();
      const body = parseJson(xhr.responseText);
      if (xhr.status >= 200 && xhr.status < 300 && body) resolve(body as CreateSurveyResponse);
      else reject(apiErrorFrom(xhr.status, body, xhr.statusText));
    };
    xhr.onerror = () => {
      cleanup();
      reject(new ApiError(0, 'NETWORK_ERROR', 'Backend not reachable — check that the service is running'));
    };
    xhr.onabort = () => {
      cleanup();
      reject(new DOMException('Upload cancelled', 'AbortError'));
    };
    xhr.send(surveyForm(files, navCsv, options));
  });
}

/**
 * Subscribe to job events; reconnects once with `resume` so no events are lost.
 * Returns a function that closes the socket.
 */
export function subscribeToJob(
  jobId: string,
  onEvent: (event: JobEvent) => void,
  options: { baseUrl?: string } = {},
): () => void {
  const base = options.baseUrl ?? `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`;
  let lastSeq = 0;
  let closed = false;
  let retried = false;
  let socket: WebSocket;

  const open = () => {
    socket = new WebSocket(`${base}/ws/jobs/${encodeURIComponent(jobId)}`);
    socket.onopen = () => {
      if (lastSeq > 0) socket.send(JSON.stringify({ type: 'resume', after_seq: lastSeq }));
    };
    socket.onmessage = (message) => {
      const event = JSON.parse(String(message.data)) as JobEvent;
      if (event.seq <= lastSeq) return;
      lastSeq = event.seq;
      onEvent(event);
    };
    socket.onclose = () => {
      const finished = lastSeq > 0 && closed;
      if (!closed && !finished && !retried && lastSeq > 0) {
        retried = true;
        open();
      }
    };
  };
  open();
  return () => {
    closed = true;
    socket.close();
  };
}
