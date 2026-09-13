/**
 * Live survey state for S-02: detections keyed by `detection_id`, track chunks, warnings and job
 * progress. WebSocket events and loaded results go through one reducer, so replayed events never
 * create duplicates (TC-UI-014) and merges move the selection (TC-WS-005).
 */
import type { Detection, JobEvent, ReportUrls, TrackGeoJson } from '../api/client';
import type { LatLon, QualitySegment } from '../map/mapController';

export type JobStatus =
  | 'idle'
  | 'queued'
  | 'running'
  | 'completed'
  | 'completed_with_warnings'
  | 'failed'
  | 'cancelled';

export interface TrackChunk {
  ping_start: number;
  ping_end: number;
  points: LatLon[];
}

export interface WarningItem {
  code: string;
  message: string;
  ping_start: number;
  ping_end: number;
}

export interface LiveState {
  detections: ReadonlyMap<string, Detection>;
  chunks: TrackChunk[];
  loadedTrack: LatLon[];
  loadedQuality: QualitySegment[];
  warnings: WarningItem[];
  stage: string | null;
  percent: number | null;
  etaS: number | null;
  pingsTotal: number | null;
  status: JobStatus;
  error: { code: string; message: string } | null;
  selectedId: string | null;
  reportUrls: Partial<ReportUrls> | null;
  lastSeq: number;
}

export const INITIAL_STATE: LiveState = {
  detections: new Map(),
  chunks: [],
  loadedTrack: [],
  loadedQuality: [],
  warnings: [],
  stage: null,
  percent: null,
  etaS: null,
  pingsTotal: null,
  status: 'idle',
  error: null,
  selectedId: null,
  reportUrls: null,
  lastSeq: 0,
};

export type LiveAction =
  | { type: 'event'; event: JobEvent }
  | { type: 'loaded'; detections: Detection[]; track: TrackGeoJson | null; status: JobStatus }
  | { type: 'select'; id: string | null }
  | { type: 'reviewed'; detection: Detection }
  | { type: 'reset'; status?: JobStatus };

const STATUSES: JobStatus[] = ['queued', 'running', 'completed', 'completed_with_warnings', 'failed', 'cancelled'];

export function statusFrom(value: string | null | undefined): JobStatus {
  return STATUSES.includes(value as JobStatus) ? (value as JobStatus) : 'idle';
}

export function isActive(status: JobStatus): boolean {
  return status === 'queued' || status === 'running';
}

function withDetection(state: LiveState, detection: Detection): LiveState {
  const detections = new Map(state.detections);
  detections.set(detection.detection_id, detection);
  return { ...state, detections };
}

/** Track line and quality segments from `GET /surveys/{id}/track` (GeoJSON `[lon, lat]`). */
export function parseTrack(track: TrackGeoJson | null): { line: LatLon[]; quality: QualitySegment[] } {
  const line: LatLon[] = [];
  const quality: QualitySegment[] = [];
  for (const feature of track?.features ?? []) {
    const points = feature.geometry.coordinates.map(([lon, lat]) => [lat, lon] as LatLon);
    const props = feature.properties ?? {};
    if (props.segment === 'quality') {
      quality.push({
        code: props.code ?? 'QUALITY',
        ping_start: props.ping_start ?? 0,
        ping_end: props.ping_end ?? 0,
        points,
      });
    } else if (!line.length) {
      line.push(...points);
    }
  }
  return { line, quality };
}

function applyEvent(state: LiveState, event: JobEvent): LiveState {
  if (typeof event.seq === 'number' && event.seq <= state.lastSeq) return state;
  const next = { ...state, lastSeq: typeof event.seq === 'number' ? event.seq : state.lastSeq };
  switch (event.type) {
    case 'progress':
      return {
        ...next,
        stage: event.stage,
        percent: event.percent,
        etaS: event.eta_s ?? null,
        pingsTotal: event.pings_total ?? next.pingsTotal,
        status: isActive(next.status) || next.status === 'idle' ? 'running' : next.status,
      };
    case 'track':
      return {
        ...next,
        chunks: [...next.chunks, { ping_start: event.ping_start, ping_end: event.ping_end, points: event.points }],
      };
    case 'detection':
    case 'detection_update':
      return withDetection(next, event.detection);
    case 'detection_removed': {
      const detections = new Map(next.detections);
      detections.delete(event.detection_id);
      let selectedId = next.selectedId;
      if (selectedId === event.detection_id) {
        selectedId = event.merged_into && detections.has(event.merged_into) ? event.merged_into : null;
      }
      return { ...next, detections, selectedId };
    }
    case 'warning':
      return {
        ...next,
        warnings: [
          ...next.warnings,
          { code: event.code, message: event.message, ping_start: event.ping_start, ping_end: event.ping_end },
        ],
      };
    case 'done':
      return {
        ...next,
        status: statusFrom(event.status) === 'idle' ? 'completed' : statusFrom(event.status),
        percent: 100,
        etaS: null,
        reportUrls: event.report_urls ?? next.reportUrls,
      };
    case 'error':
      return { ...next, status: 'failed', error: { code: event.code, message: event.message } };
  }
}

export function liveReducer(state: LiveState, action: LiveAction): LiveState {
  switch (action.type) {
    case 'reset':
      return { ...INITIAL_STATE, detections: new Map(), status: action.status ?? 'idle' };
    case 'select':
      return { ...state, selectedId: action.id };
    case 'reviewed':
      return state.detections.has(action.detection.detection_id) ? withDetection(state, action.detection) : state;
    case 'loaded': {
      const { line, quality } = parseTrack(action.track);
      return {
        ...state,
        detections: new Map(action.detections.map((d) => [d.detection_id, d])),
        loadedTrack: line,
        loadedQuality: quality,
        warnings: quality.map((q) => ({
          code: q.code,
          message: `${q.code} pings ${q.ping_start}–${q.ping_end}`,
          ping_start: q.ping_start,
          ping_end: q.ping_end,
        })),
        status: action.status,
      };
    }
    case 'event':
      return applyEvent(state, action.event);
  }
}

export function trackPointsOf(chunks: TrackChunk[], loaded: LatLon[]): LatLon[] {
  return chunks.length ? chunks.flatMap((chunk) => chunk.points) : loaded;
}

/** Track points of a ping range, interpolating ping numbers inside each chunk's sampled points. */
export function pointsForPings(chunks: TrackChunk[], start: number, end: number): LatLon[] {
  const out: LatLon[] = [];
  let nearest: { point: LatLon; distance: number } | null = null;
  for (const chunk of chunks) {
    const n = chunk.points.length;
    chunk.points.forEach((point, i) => {
      const ping = n === 1 ? chunk.ping_start : chunk.ping_start + ((chunk.ping_end - chunk.ping_start) * i) / (n - 1);
      if (ping >= start && ping <= end) out.push(point);
      const distance = Math.min(Math.abs(ping - start), Math.abs(ping - end));
      if (!nearest || distance < nearest.distance) nearest = { point, distance };
    });
  }
  if (!out.length && nearest) out.push((nearest as { point: LatLon }).point);
  return out;
}

const DRAWN_CODES = new Set(['DROPOUT', 'HIGH_MOTION']);

export function qualitySegmentsOf(
  chunks: TrackChunk[],
  warnings: WarningItem[],
  loaded: QualitySegment[],
): QualitySegment[] {
  if (!chunks.length) return loaded;
  return warnings
    .filter((w) => DRAWN_CODES.has(w.code))
    .map((w) => ({ code: w.code, ping_start: w.ping_start, ping_end: w.ping_end, points: pointsForPings(chunks, w.ping_start, w.ping_end) }));
}

export function warningPoints(chunks: TrackChunk[], loaded: QualitySegment[], warning: WarningItem): LatLon[] {
  if (chunks.length) return pointsForPings(chunks, warning.ping_start, warning.ping_end);
  return (
    loaded.find((q) => q.code === warning.code && q.ping_start === warning.ping_start && q.ping_end === warning.ping_end)
      ?.points ?? []
  );
}
