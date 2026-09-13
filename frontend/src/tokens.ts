/**
 * Class and tier styling shared by map markers, lists and exports (docs/wireframes/README.md §4).
 * Values mirror src/styles/tokens.css; a unit test checks they stay in sync.
 */
export type DetectionClass =
  | 'ghost_net'
  | 'shipwreck'
  | 'pipe'
  | 'cylinder'
  | 'debris_other'
  | 'unknown_anomaly';

export type AlertTier = 'hazard' | 'review' | 'anomaly' | 'hidden';

export interface ClassStyle {
  label: string;
  color: string;
  shape: 'diamond' | 'triangle' | 'bar' | 'circle' | 'square' | 'hexagon';
  cssVar: string;
}

export const CLASS_STYLES: Record<DetectionClass, ClassStyle> = {
  ghost_net: { label: 'Ghost net', color: '#e5484d', shape: 'diamond', cssVar: '--class-ghost-net' },
  shipwreck: { label: 'Shipwreck', color: '#8e4ec6', shape: 'triangle', cssVar: '--class-shipwreck' },
  pipe: { label: 'Pipe', color: '#f76b15', shape: 'bar', cssVar: '--class-pipe' },
  cylinder: { label: 'Cylinder', color: '#ffb224', shape: 'circle', cssVar: '--class-cylinder' },
  debris_other: {
    label: 'Other debris',
    color: '#0090ff',
    shape: 'square',
    cssVar: '--class-debris-other',
  },
  unknown_anomaly: {
    label: 'Unknown anomaly',
    color: '#d6409f',
    shape: 'hexagon',
    cssVar: '--class-unknown-anomaly',
  },
};

export const TIER_LABELS: Record<AlertTier, string> = {
  hazard: 'HAZARD',
  review: 'REVIEW',
  anomaly: 'ANOMALY',
  hidden: 'LOW',
};

/** Draw order: hazards on top. */
export const TIER_Z: Record<AlertTier, number> = { hazard: 400, review: 300, anomaly: 200, hidden: 100 };

/** Screen-reader label, e.g. "Ghost net, 87 percent, hazard, 13.084120 north, 80.312750 east". */
export function describeDetection(
  cls: DetectionClass,
  confidence: number,
  tier: AlertTier,
  lat: number | null,
  lon: number | null,
): string {
  const where =
    lat === null || lon === null
      ? 'not geotagged'
      : `${Math.abs(lat).toFixed(6)} ${lat >= 0 ? 'north' : 'south'}, ${Math.abs(lon).toFixed(6)} ${
          lon >= 0 ? 'east' : 'west'
        }`;
  return `${CLASS_STYLES[cls].label}, ${Math.round(confidence)} percent, ${tier}, ${where}`;
}
