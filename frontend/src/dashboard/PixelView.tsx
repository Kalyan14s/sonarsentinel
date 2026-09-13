import type { Detection } from '../api/client';
import { CLASS_STYLES, describeDetection, type AlertTier, type DetectionClass } from '../tokens';

interface PixelViewProps {
  detections: readonly Detection[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

/** Replaces the map for image inputs without navigation: detection boxes in pixel coordinates. */
export function PixelView({ detections, selectedId, onSelect }: PixelViewProps) {
  const boxed = detections.filter((d) => d.sonar_ref.pixel_bbox);
  const box = (d: Detection) => d.sonar_ref.pixel_bbox as [number, number, number, number];
  const width = Math.max(1, ...boxed.map((d) => box(d)[2]));
  const height = Math.max(1, ...boxed.map((d) => box(d)[3]));
  return (
    <svg
      role="img"
      aria-label={`Pixel view of ${boxed.length} detections`}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', background: 'var(--color-surface-muted)' }}
    >
      {boxed.map((d) => {
        const [x1, y1, x2, y2] = d.sonar_ref.pixel_bbox as [number, number, number, number];
        const cls = d.class as DetectionClass;
        const selected = d.detection_id === selectedId;
        return (
          <rect
            key={d.detection_id}
            x={x1}
            y={y1}
            width={Math.max(x2 - x1, 1)}
            height={Math.max(y2 - y1, 1)}
            fill={CLASS_STYLES[cls].color}
            fillOpacity={0.15}
            stroke={CLASS_STYLES[cls].color}
            strokeWidth={selected ? 6 : 3}
            vectorEffect="non-scaling-stroke"
            onClick={() => onSelect(d.detection_id)}
            style={{ cursor: 'pointer' }}
          >
            <title>{describeDetection(cls, d.confidence, d.alert_tier as AlertTier, null, null)}</title>
          </rect>
        );
      })}
    </svg>
  );
}
