import type { Detection, DetectionSort, QualityFlag, ReviewStatus } from '../api/client';
import { formatDd } from '../geo/format';

/** Plain-language tooltips for quality flags (S-03 component 7). */
export const FLAG_HELP: Record<QualityFlag, string> = {
  DROPOUT: 'Part of this object lies on missing sonar data',
  HIGH_MOTION: 'The towfish was rolling, pitching or turning quickly here',
  NEAR_NADIR: 'Close to the track, where sonar geometry is least reliable',
  SURFACE_RETURN_BAND: 'Inside the sea-surface echo band',
  TILE_EDGE: 'Cut by the edge of the swath',
  GPS_INTERPOLATED: 'Position interpolated across a GPS gap',
  LAYBACK_ESTIMATED: 'Towfish position estimated from cable length',
  HEADING_FROM_COG: 'Heading taken from course over ground',
  NO_ALTITUDE_BOTTOM_TRACKED: 'Altitude found by bottom tracking, not recorded',
  NOT_GEOTAGGED: 'No navigation: pixel coordinates only',
};

export const REVIEW_LABELS: Record<ReviewStatus, string> = {
  pending: 'Pending',
  confirmed: 'Confirmed',
  rejected: 'Rejected',
  reclassified: 'Reclassified',
};

export const SORT_OPTIONS: { value: DetectionSort; label: string }[] = [
  { value: '-confidence', label: 'Confidence (high first)' },
  { value: 'confidence', label: 'Confidence (low first)' },
  { value: '-area', label: 'Size (large first)' },
  { value: 'ping', label: 'Along track' },
  { value: 'class', label: 'Class' },
];

/** `SRV-20260913-001-D0003` → `D3`. */
export function shortId(detectionId: string): string {
  const match = /-D(\d+)$/.exec(detectionId);
  return match ? `D${Number(match[1])}` : detectionId;
}

/** List-card location: `lat, lon` with 6 decimals, or the pixel box for images without GPS. */
export function locationText(d: Detection): string {
  const { lat, lon } = d.position;
  if (lat !== null && lon !== null) return `${formatDd(lat)}, ${formatDd(lon)}`;
  const box = d.sonar_ref.pixel_bbox;
  return box ? `pixel x ${box[0]}–${box[2]}, y ${box[1]}–${box[3]}` : 'no position';
}

export function sizeText(d: Detection): string {
  const { length_m, width_m } = d.dimensions;
  return length_m !== null && width_m !== null ? `${length_m} × ${width_m} m` : 'size n/a';
}
