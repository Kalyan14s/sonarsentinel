/**
 * Client-side filters for S-02 (ST-093). Semantics match `GET /surveys/{id}/detections`, so the
 * "current filters" report scope returns exactly the rows the map shows:
 * class/tier/review status are membership tests, confidence bounds are inclusive and a detection
 * passes the flag filter when it carries any of the selected flags.
 */
import type { Detection, DetectionQuery, DetectionSort, QualityFlag, ReviewStatus } from '../api/client';
import type { AlertTier, DetectionClass } from '../tokens';

export const ALL_CLASSES: DetectionClass[] = [
  'ghost_net',
  'shipwreck',
  'pipe',
  'cylinder',
  'debris_other',
  'unknown_anomaly',
];
export const ALL_TIERS: AlertTier[] = ['hazard', 'review', 'anomaly', 'hidden'];
export const DEFAULT_TIERS: AlertTier[] = ['hazard', 'review', 'anomaly'];
export const ALL_REVIEW_STATUSES: ReviewStatus[] = ['pending', 'confirmed', 'rejected', 'reclassified'];
export const FILTERABLE_FLAGS: QualityFlag[] = [
  'DROPOUT',
  'HIGH_MOTION',
  'NEAR_NADIR',
  'TILE_EDGE',
  'GPS_INTERPOLATED',
  'LAYBACK_ESTIMATED',
  'SURFACE_RETURN_BAND',
];
const SORTS: DetectionSort[] = ['confidence', '-confidence', 'area', '-area', 'ping', '-ping', 'class'];

export interface Filters {
  classes: DetectionClass[];
  minConf: number;
  maxConf: number;
  tiers: AlertTier[];
  /** Any of these flags; empty = no flag filter. */
  flags: QualityFlag[];
  /** Empty = any review status. */
  reviewStatuses: ReviewStatus[];
  sort: DetectionSort;
}

export const DEFAULT_FILTERS: Filters = {
  classes: ALL_CLASSES,
  minConf: 30,
  maxConf: 100,
  tiers: DEFAULT_TIERS,
  flags: [],
  reviewStatuses: [],
  sort: '-confidence',
};

type NumericKey = 'confidence' | 'area' | 'ping';
const NUMERIC: Record<NumericKey, (d: Detection) => number> = {
  confidence: (d) => d.confidence,
  area: (d) => d.dimensions.area_m2 ?? 0,
  ping: (d) => d.sonar_ref.ping_start ?? 0,
};

export function sortDetections(list: readonly Detection[], sort: DetectionSort): Detection[] {
  const out = [...list];
  if (sort === 'class') {
    return out.sort((a, b) => a.class.localeCompare(b.class) || b.confidence - a.confidence);
  }
  const descending = sort.startsWith('-');
  const key = NUMERIC[(descending ? sort.slice(1) : sort) as NumericKey];
  return out.sort(
    (a, b) => (descending ? key(b) - key(a) : key(a) - key(b)) || a.detection_id.localeCompare(b.detection_id),
  );
}

export function filterDetections(list: readonly Detection[], filters: Filters): Detection[] {
  const classes = new Set<string>(filters.classes);
  const tiers = new Set<string>(filters.tiers);
  const statuses = new Set<string>(filters.reviewStatuses);
  const flags = new Set<string>(filters.flags);
  return list.filter(
    (d) =>
      classes.has(d.class) &&
      d.confidence >= filters.minConf &&
      d.confidence <= filters.maxConf &&
      tiers.has(d.alert_tier) &&
      (statuses.size === 0 || statuses.has(d.review.status)) &&
      (flags.size === 0 || d.quality_flags.some((flag) => flags.has(flag))),
  );
}

export function filterAndSort(list: readonly Detection[], filters: Filters): Detection[] {
  return sortDetections(filterDetections(list, filters), filters.sort);
}

export interface Counts {
  classes: Record<string, number>;
  tiers: Record<string, number>;
}

export function countDetections(list: readonly Detection[]): Counts {
  const counts: Counts = { classes: {}, tiers: {} };
  for (const d of list) {
    counts.classes[d.class] = (counts.classes[d.class] ?? 0) + 1;
    counts.tiers[d.alert_tier] = (counts.tiers[d.alert_tier] ?? 0) + 1;
  }
  return counts;
}

const sameSet = (a: readonly string[], b: readonly string[]) =>
  a.length === b.length && a.every((value) => b.includes(value));

function listParam<T extends string>(params: URLSearchParams, key: string, allowed: readonly T[], fallback: T[]): T[] {
  const raw = params.get(key);
  if (raw === null) return fallback;
  return raw
    .split(',')
    .filter((value): value is T => (allowed as readonly string[]).includes(value));
}

function numberParam(params: URLSearchParams, key: string, fallback: number): number {
  const value = Number(params.get(key));
  return params.has(key) && Number.isFinite(value) ? Math.min(Math.max(value, 0), 100) : fallback;
}

/** Filters from the page URL (shareable view); unknown values are ignored. */
export function filtersFromSearch(params: URLSearchParams): Filters {
  const sort = params.get('sort') as DetectionSort | null;
  return {
    classes: listParam(params, 'class', ALL_CLASSES, DEFAULT_FILTERS.classes),
    minConf: numberParam(params, 'min_conf', DEFAULT_FILTERS.minConf),
    maxConf: numberParam(params, 'max_conf', DEFAULT_FILTERS.maxConf),
    tiers: listParam(params, 'tier', ALL_TIERS, DEFAULT_FILTERS.tiers),
    flags: listParam(params, 'flags', FILTERABLE_FLAGS, []),
    reviewStatuses: listParam(params, 'review_status', ALL_REVIEW_STATUSES, []),
    sort: sort && SORTS.includes(sort) ? sort : DEFAULT_FILTERS.sort,
  };
}

/** Writes non-default filters into a copy of `base`, keeping other parameters such as `job`. */
export function filtersToSearch(filters: Filters, base?: URLSearchParams): URLSearchParams {
  const params = new URLSearchParams(base);
  for (const key of ['class', 'min_conf', 'max_conf', 'tier', 'flags', 'review_status', 'sort']) params.delete(key);
  if (!sameSet(filters.classes, DEFAULT_FILTERS.classes)) params.set('class', filters.classes.join(','));
  if (filters.minConf !== DEFAULT_FILTERS.minConf) params.set('min_conf', String(filters.minConf));
  if (filters.maxConf !== DEFAULT_FILTERS.maxConf) params.set('max_conf', String(filters.maxConf));
  if (!sameSet(filters.tiers, DEFAULT_FILTERS.tiers)) params.set('tier', filters.tiers.join(','));
  if (filters.flags.length) params.set('flags', filters.flags.join(','));
  if (filters.reviewStatuses.length) params.set('review_status', filters.reviewStatuses.join(','));
  if (filters.sort !== DEFAULT_FILTERS.sort) params.set('sort', filters.sort);
  return params;
}

/** The same filters as API query parameters (report scope `filtered`). */
export function toDetectionQuery(filters: Filters): DetectionQuery {
  return {
    class: sameSet(filters.classes, ALL_CLASSES) ? undefined : filters.classes,
    tier: filters.tiers,
    min_conf: filters.minConf,
    max_conf: filters.maxConf,
    review_status: filters.reviewStatuses.length ? filters.reviewStatuses : undefined,
    flags: filters.flags.length ? filters.flags : undefined,
  };
}
