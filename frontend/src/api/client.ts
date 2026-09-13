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

export type JobEvent =
  | { type: 'progress'; seq: number; stage: string; percent: number; pings_done?: number; pings_total?: number }
  | { type: 'track'; seq: number; points: [number, number][]; ping_start: number; ping_end: number }
  | { type: 'detection'; seq: number; detection: Detection }
  | { type: 'warning'; seq: number; code: string; message: string; ping_start: number; ping_end: number }
  | { type: 'done'; seq: number; status: string; summary: Report['summary'] }
  | { type: 'error'; seq: number; code: string; message: string };

const API = '/api/v1';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, init);
  if (!response.ok) {
    let body: ApiErrorBody | undefined;
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      body = undefined;
    }
    throw new ApiError(
      response.status,
      body?.error.code ?? 'INTERNAL_ERROR',
      body?.error.message ?? response.statusText,
      body?.error.details,
    );
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

export const api = {
  health: () => request<{ status: string; version: string; runtime: string }>('/health'),
  surveys: () => request<Paged<SurveySummary>>('/surveys'),
  survey: (id: string) => request<SurveySummary>(`/surveys/${encodeURIComponent(id)}`),
  track: (id: string) => request<TrackGeoJson>(`/surveys/${encodeURIComponent(id)}/track`),
  detections: (id: string, query: DetectionQuery = {}) =>
    request<Paged<Detection>>(`/surveys/${encodeURIComponent(id)}/detections${detectionQueryString(query)}`),
  reportUrl: (id: string, format: 'json' | 'csv') =>
    `${API}/surveys/${encodeURIComponent(id)}/report?format=${format}`,
};

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
