/**
 * Typed client for the SonarSentinel API (docs/architecture/05-api-specification.md, ADR-018).
 * Report and detection types are generated from the backend JSON Schema (npm run gen:types).
 */
import type { SonarSentinelDetectionReport10 as Report } from './report-schema';

export type { Report };
export type Detection = Report['detections'][number];
export type ReviewStatus = Detection['review']['status'];
export type RejectReason = NonNullable<Detection['review']['reject_reason']>;
export type QualityFlag = Detection['quality_flags'][number];

export type ReportFormat = 'json' | 'csv' | 'geojson' | 'kml';
export type ReportScope = 'all' | 'filtered' | 'hazards' | 'confirmed';
export type ChipOverlay = 'mask' | 'shadow' | 'anomaly' | 'none';
export type ReportUrls = Record<ReportFormat, string>;

export const REPORT_FORMATS: ReportFormat[] = ['json', 'csv', 'geojson', 'kml'];
export const REJECT_REASONS: RejectReason[] = ['rock', 'shadow', 'ripples', 'noise', 'other'];

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
  report_urls?: Partial<ReportUrls>;
  mosaic?: MosaicInfo | null;
}

/** Mosaic PNG and Leaflet bounds `[[south, west], [north, east]]` (ST-036). */
export interface MosaicInfo {
  url: string;
  bounds: [[number, number], [number, number]];
}

export interface Paged<T> {
  total: number;
  items: T[];
}

export interface TrackProperties {
  segment?: 'track' | 'quality';
  code?: string;
  ping_start?: number;
  ping_end?: number;
}

/** `GET /surveys/{id}/track`: coordinates are GeoJSON `[lon, lat]`. */
export interface TrackGeoJson {
  type: 'FeatureCollection';
  features: {
    type: 'Feature';
    properties?: TrackProperties | null;
    geometry: { type: 'LineString'; coordinates: [number, number][] };
  }[];
}

export type DetectionSort = 'confidence' | '-confidence' | 'area' | '-area' | 'ping' | '-ping' | 'class';

export interface DetectionQuery {
  class?: string[];
  min_conf?: number;
  max_conf?: number;
  tier?: string[];
  review_status?: string[];
  flags?: string[];
  bbox?: [number, number, number, number];
  sort?: DetectionSort;
  limit?: number;
  offset?: number;
}

export interface ReviewRequest {
  review_status: ReviewStatus;
  class?: string;
  reject_reason?: RejectReason;
  note?: string;
  reviewer?: string;
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

interface EventBase {
  seq: number;
  job_id?: string;
  ts?: string;
}

/** WebSocket messages of `/ws/jobs/{job_id}` (API spec §3). */
export type JobEvent =
  | (EventBase & {
      type: 'progress';
      stage: string;
      percent: number;
      eta_s?: number | null;
      pings_done?: number;
      pings_total?: number;
    })
  | (EventBase & { type: 'track'; points: [number, number][]; ping_start: number; ping_end: number })
  | (EventBase & { type: 'detection'; detection: Detection })
  | (EventBase & { type: 'detection_update'; detection: Detection })
  | (EventBase & { type: 'detection_removed'; detection_id: string; merged_into?: string | null })
  | (EventBase & { type: 'warning'; code: string; message: string; ping_start: number; ping_end: number })
  | (EventBase & {
      type: 'done';
      status: string;
      summary: Report['summary'];
      report_urls?: Partial<ReportUrls>;
      mosaic?: MosaicInfo | null;
    })
  | (EventBase & { type: 'error'; code: string; message: string });

export type ConnectionStatus = 'connecting' | 'live' | 'reconnecting' | 'closed';

const API = '/api/v1';
const enc = encodeURIComponent;

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

function filterParams(params: URLSearchParams, query: DetectionQuery): void {
  if (query.class?.length) params.set('class', query.class.join(','));
  if (query.tier?.length) params.set('tier', query.tier.join(','));
  if (query.min_conf !== undefined) params.set('min_conf', String(query.min_conf));
  if (query.max_conf !== undefined) params.set('max_conf', String(query.max_conf));
  if (query.review_status?.length) params.set('review_status', query.review_status.join(','));
  if (query.flags?.length) params.set('flags', query.flags.join(','));
  if (query.bbox) params.set('bbox', query.bbox.join(','));
}

export function detectionQueryString(query: DetectionQuery): string {
  const params = new URLSearchParams();
  filterParams(params, query);
  if (query.sort) params.set('sort', query.sort);
  if (query.limit !== undefined) params.set('limit', String(query.limit));
  if (query.offset !== undefined) params.set('offset', String(query.offset));
  const text = params.toString();
  return text ? `?${text}` : '';
}

export interface ReportOptions {
  scope?: ReportScope;
  includeRejected?: boolean;
  /** Detection filters, sent only with `scope: 'filtered'`. */
  filters?: DetectionQuery;
}

export function reportQueryString(format: ReportFormat, options: ReportOptions = {}): string {
  const params = new URLSearchParams({ format, scope: options.scope ?? 'all' });
  if (options.scope === 'filtered' && options.filters) filterParams(params, options.filters);
  if (options.includeRejected) params.set('include_rejected', 'true');
  return `?${params.toString()}`;
}

/** Multipart form shared by validate and create: `files`, optional `nav_csv`, `options` JSON. */
export function surveyForm(files: File[], navCsv?: File | null, options?: SurveyOptions): FormData {
  const form = new FormData();
  for (const file of files) form.append('files', file, file.name);
  if (navCsv) form.append('nav_csv', navCsv, navCsv.name);
  if (options) form.append('options', JSON.stringify(options));
  return form;
}

/** `GET /surveys` row (ADR-019): the survey summary plus history columns. */
export interface SurveyListItem extends SurveySummary {
  project?: string | null;
  status?: string;
  warning_count?: number;
  size_bytes?: number | null;
  error_code?: string | null;
}

/** `GET /surveys` query (S-07 history filters). */
export interface SurveyListQuery {
  q?: string;
  project?: string;
  status?: string[];
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
}

export function surveyListQueryString(query: SurveyListQuery): string {
  const params = new URLSearchParams();
  if (query.q?.trim()) params.set('q', query.q.trim());
  if (query.project) params.set('project', query.project);
  if (query.status?.length) params.set('status', query.status.join(','));
  if (query.from) params.set('from', query.from);
  if (query.to) params.set('to', query.to);
  if (query.limit !== undefined) params.set('limit', String(query.limit));
  if (query.offset !== undefined) params.set('offset', String(query.offset));
  const text = params.toString();
  return text ? `?${text}` : '';
}

export type Basemap = 'online' | 'offline';
export type CoordinateFormat = 'dd' | 'dms';

/** Editable part of `GET/PUT /settings` (S-07, ADR-019). */
export interface EditableSettings {
  detection: { model_id: string; runtime: string; min_raw_score: number };
  anomaly: { enabled: boolean; threshold: number };
  tiers: { hazard: number; review: number; anomaly: number };
  map: { min_conf_default: number; basemap: Basemap; coordinates: CoordinateFormat };
  processing: { ground_resolution_m: number; pings_per_chunk: number; overlap_pings: number };
  geo: { apply_layback: string; cluster_radius_m: number };
}

export interface SystemSettings {
  data_dir: string;
  max_upload_gb: number;
  keep_work_files: boolean;
  offline_tiles_available: boolean;
  runtimes_available: string[];
  version: string;
}

export interface Settings extends EditableSettings {
  system: SystemSettings;
}

export interface HealthInfo {
  status: string;
  version: string;
  runtime: string;
  offline_tiles?: boolean;
}

async function requestNoContent(path: string, init?: RequestInit): Promise<void> {
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
}

export const api = {
  health: () => request<HealthInfo>('/health'),
  models: () => request<Paged<ModelInfo>>('/models'),
  surveys: (query: SurveyListQuery = {}) =>
    request<Paged<SurveyListItem>>(`/surveys${surveyListQueryString(query)}`),
  deleteSurvey: (id: string) => requestNoContent(`/surveys/${enc(id)}`, { method: 'DELETE' }),
  settings: () => request<Settings>('/settings'),
  saveSettings: (body: Partial<EditableSettings>) =>
    request<Settings>('/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  survey: (id: string) => request<SurveySummary>(`/surveys/${enc(id)}`),
  track: (id: string) => request<TrackGeoJson>(`/surveys/${enc(id)}/track`),
  detections: (id: string, query: DetectionQuery = {}) =>
    request<Paged<Detection>>(`/surveys/${enc(id)}/detections${detectionQueryString(query)}`),
  detection: (id: string) => request<Detection>(`/detections/${enc(id)}`),
  reviewDetection: (id: string, body: ReviewRequest) =>
    request<Detection>(`/detections/${enc(id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  cancelJob: (jobId: string) =>
    request<{ job_id: string; status: string }>(`/jobs/${enc(jobId)}/cancel`, { method: 'POST' }),
  reportUrl: (id: string, format: ReportFormat, options: ReportOptions = {}) =>
    `${API}/surveys/${enc(id)}/report${reportQueryString(format, options)}`,
  chipUrl: (id: string, overlay: ChipOverlay = 'mask') =>
    `${API}/detections/${enc(id)}/chip.png?overlay=${overlay}`,
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

/** Close codes of `/ws/jobs/{id}` (ADR-018). */
export const WS_CLOSE_NORMAL = 1000;
export const WS_CLOSE_UNKNOWN_JOB = 4404;
const WS_OPEN = 1;

export interface SubscribeOptions {
  baseUrl?: string;
  onStatus?: (status: ConnectionStatus) => void;
  /** Injected in tests. */
  WebSocketImpl?: typeof WebSocket;
  pingIntervalMs?: number;
  initialBackoffMs?: number;
  maxBackoffMs?: number;
}

/**
 * Follow a job's events (TC-WS-004, TC-UI-014). Sends `resume` with the last seen `seq` on every
 * (re)connect, drops duplicates, pings every 20 s and reconnects with exponential backoff (≤ 10 s)
 * until the job ends (`done`/`error`), the server reports an unknown job (4404) or the caller
 * unsubscribes. Returns the unsubscribe function.
 */
export function subscribeToJob(
  jobId: string,
  onEvent: (event: JobEvent) => void,
  options: SubscribeOptions = {},
): () => void {
  const {
    onStatus,
    WebSocketImpl = WebSocket,
    pingIntervalMs = 20_000,
    initialBackoffMs = 500,
    maxBackoffMs = 10_000,
  } = options;
  const base = options.baseUrl ?? `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`;
  let lastSeq = 0;
  let attempt = 0;
  let stopped = false;
  let finished = false;
  let socket: WebSocket | null = null;
  let pingTimer: ReturnType<typeof setInterval> | undefined;
  let retryTimer: ReturnType<typeof setTimeout> | undefined;

  const connect = () => {
    onStatus?.(attempt === 0 ? 'connecting' : 'reconnecting');
    const ws = new WebSocketImpl(`${base}/ws/jobs/${enc(jobId)}`);
    socket = ws;
    ws.onopen = () => {
      attempt = 0;
      ws.send(JSON.stringify({ type: 'resume', after_seq: lastSeq }));
      onStatus?.('live');
      pingTimer = setInterval(() => {
        if (ws.readyState === WS_OPEN) ws.send(JSON.stringify({ type: 'ping' }));
      }, pingIntervalMs);
    };
    ws.onmessage = (message) => {
      const event = parseJson(String(message.data)) as JobEvent | { type: 'pong' } | undefined;
      if (!event || event.type === 'pong') return;
      if (typeof event.seq === 'number') {
        if (event.seq <= lastSeq) return;
        lastSeq = event.seq;
      }
      if (event.type === 'done' || event.type === 'error') finished = true;
      onEvent(event);
    };
    ws.onclose = (close) => {
      clearInterval(pingTimer);
      if (stopped || finished || close.code === WS_CLOSE_UNKNOWN_JOB) {
        onStatus?.('closed');
        return;
      }
      attempt += 1;
      onStatus?.('reconnecting');
      retryTimer = setTimeout(connect, Math.min(initialBackoffMs * 2 ** (attempt - 1), maxBackoffMs));
    };
  };

  connect();
  return () => {
    stopped = true;
    clearInterval(pingTimer);
    clearTimeout(retryTimer);
    socket?.close();
  };
}
