import L from './leaflet';
import 'leaflet.markercluster';

import type { Detection } from '../api/client';
import { describeDetection, TIER_Z, type AlertTier, type DetectionClass } from '../tokens';
import { markerHtml } from './markers';

export type LatLon = [number, number];

export interface QualitySegment {
  code: string;
  ping_start: number;
  ping_end: number;
  points: LatLon[];
}

/** Georeferenced mosaic (ST-036): PNG URL and Leaflet bounds `[[south, west], [north, east]]`. */
export interface MosaicOverlay {
  url: string;
  bounds: [LatLon, LatLon];
}

/**
 * Imperative map API. Layers are updated incrementally so thousands of streamed detections stay
 * smooth (S-02: ≥ 30 fps with 2,000 markers); pages talk to the map only through this interface,
 * which tests replace with a spy.
 */
export interface MapController {
  setTrack(points: LatLon[]): void;
  setQualitySegments(segments: QualitySegment[]): void;
  setMosaic(mosaic: MosaicOverlay | null): void;
  setDetections(detections: readonly Detection[]): void;
  select(detection: Detection | null): void;
  zoomToPoints(points: LatLon[]): void;
  destroy(): void;
}

const DEFAULT_TILES = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const FOOTPRINT_MIN_ZOOM = 17;
const QUALITY_STYLES: Record<string, L.PolylineOptions> = {
  DROPOUT: { color: '#c2272d', weight: 7, opacity: 0.85, dashArray: '2 5', className: 'ss-quality-dropout' },
  HIGH_MOTION: { color: '#b35c00', weight: 5, opacity: 0.9, dashArray: '10 6', className: 'ss-quality-motion' },
};

function located(det: Detection): LatLon | null {
  const { lat, lon } = det.position;
  return lat === null || lon === null ? null : [lat, lon];
}

function icon(det: Detection, selected: boolean): L.DivIcon {
  return L.divIcon({
    className: selected ? 'ss-marker-wrap ss-selected' : 'ss-marker-wrap',
    html: markerHtml(det.class as DetectionClass, det.alert_tier as AlertTier),
    iconSize: [22, 22],
  });
}

function label(det: Detection): string {
  const { lat, lon } = det.position;
  return describeDetection(det.class as DetectionClass, det.confidence, det.alert_tier as AlertTier, lat, lon);
}

export function createMapController(
  element: HTMLElement,
  options: { tileUrl?: string; onSelect?: (id: string) => void; reducedMotion?: boolean } = {},
): MapController {
  const animate = !options.reducedMotion;
  const map = L.map(element).setView([13.08, 80.3], 13);
  const tiles = options.tileUrl ?? DEFAULT_TILES;
  L.tileLayer(tiles, {
    maxZoom: 20,
    // Local tiles (ST-099) are self-rendered OSM data; keep the attribution either way.
    attribution: tiles.startsWith('/')
      ? '&copy; OpenStreetMap contributors (offline)'
      : '&copy; OpenStreetMap contributors',
  }).addTo(map);

  const track = L.polyline([], { className: 'ss-track', weight: 3 }).addTo(map);
  const labelIcon = (text: string) => L.divIcon({ className: 'ss-track-label', html: text, iconSize: [18, 18] });
  const start = L.marker([0, 0], { icon: labelIcon('S'), interactive: false, keyboard: false });
  const vessel = L.marker([0, 0], { icon: labelIcon('&gt;'), interactive: false, keyboard: false });
  const quality = L.layerGroup().addTo(map);
  const cluster = L.markerClusterGroup({
    chunkedLoading: true,
    showCoverageOnHover: false,
    disableClusteringAtZoom: FOOTPRINT_MIN_ZOOM,
    maxClusterRadius: 48,
  }).addTo(map);
  const footprints = L.layerGroup();
  const entries = new Map<string, { marker: L.Marker; det: Detection; footprint: L.Polygon | null }>();
  let trackPoints: LatLon[] = [];
  let selectedId: string | null = null;
  let uncertainty: L.Circle | null = null;
  let userMoved = false;
  let programmatic = false;
  let fitPending = false;
  let mosaicLayer: L.ImageOverlay | null = null;

  map.on('dragstart', () => {
    userMoved = true;
  });
  map.on('zoomstart', () => {
    if (!programmatic) userMoved = true;
  });
  map.on('moveend', () => {
    programmatic = false;
  });
  map.on('zoomend', () => {
    const show = map.getZoom() >= FOOTPRINT_MIN_ZOOM;
    if (show && !map.hasLayer(footprints)) footprints.addTo(map);
    if (!show && map.hasLayer(footprints)) footprints.remove();
  });

  const fitTo = (points: LatLon[]) => {
    const first = points[0];
    if (!first) return;
    programmatic = true;
    if (points.length === 1) map.setView(first, 18, { animate });
    else map.fitBounds(L.latLngBounds(points), { padding: [32, 32], maxZoom: 18, animate });
  };

  const scheduleFit = () => {
    if (userMoved || fitPending) return;
    fitPending = true;
    requestAnimationFrame(() => {
      fitPending = false;
      if (userMoved) return;
      const points: LatLon[] = [...trackPoints];
      for (const { det } of entries.values()) {
        const where = located(det);
        if (where) points.push(where);
      }
      fitTo(points);
    });
  };

  const footprintFor = (det: Detection): L.Polygon | null => {
    const ring = det.footprint as unknown as LatLon[] | null;
    if (!ring || ring.length < 3) return null;
    return L.polygon(ring, { className: 'ss-footprint', weight: 1, fillOpacity: 0.12, interactive: false });
  };

  return {
    setTrack(points) {
      trackPoints = points;
      track.setLatLngs(points);
      const first = points[0];
      const last = points[points.length - 1];
      if (first && last) {
        start.setLatLng(first).addTo(map);
        vessel.setLatLng(last).addTo(map);
      } else {
        start.remove();
        vessel.remove();
      }
      scheduleFit();
    },

    setQualitySegments(segments) {
      quality.clearLayers();
      for (const segment of segments) {
        if (segment.points.length < 2) continue;
        const style = QUALITY_STYLES[segment.code] ?? { color: '#b35c00', weight: 4, dashArray: '4 4' };
        L.polyline(segment.points, style)
          .bindTooltip(`${segment.code} · pings ${segment.ping_start}–${segment.ping_end}`)
          .addTo(quality);
      }
    },

    setMosaic(mosaic) {
      mosaicLayer?.remove();
      mosaicLayer = null;
      if (!mosaic) return;
      mosaicLayer = L.imageOverlay(mosaic.url, mosaic.bounds, {
        opacity: 0.75,
        className: 'ss-mosaic',
        interactive: false,
      }).addTo(map);
      mosaicLayer.bringToBack();
    },

    setDetections(detections) {
      const next = new Map<string, Detection>();
      for (const det of detections) if (located(det)) next.set(det.detection_id, det);
      const removed: L.Layer[] = [];
      const added: L.Layer[] = [];
      for (const [id, entry] of entries) {
        if (next.has(id)) continue;
        removed.push(entry.marker);
        if (entry.footprint) footprints.removeLayer(entry.footprint);
        entries.delete(id);
      }
      for (const det of next.values()) {
        const where = located(det) as LatLon;
        const selected = det.detection_id === selectedId;
        const entry = entries.get(det.detection_id);
        if (entry?.det === det) continue;
        const z = TIER_Z[det.alert_tier as AlertTier] + (selected ? 1000 : 0);
        if (entry) {
          entry.marker.setLatLng(where).setIcon(icon(det, selected)).setZIndexOffset(z);
          entry.marker.setOpacity(det.alert_tier === 'hidden' ? 0.5 : 1);
          if (entry.footprint) footprints.removeLayer(entry.footprint);
          entry.footprint = footprintFor(det);
          entry.footprint?.addTo(footprints);
          entry.det = det;
          continue;
        }
        const marker = L.marker(where, {
          icon: icon(det, selected),
          keyboard: true,
          title: label(det),
          alt: label(det),
          zIndexOffset: z,
          opacity: det.alert_tier === 'hidden' ? 0.5 : 1,
        });
        marker.bindTooltip(label(det));
        marker.on('click', () => options.onSelect?.(det.detection_id));
        const footprint = footprintFor(det);
        footprint?.addTo(footprints);
        entries.set(det.detection_id, { marker, det, footprint });
        added.push(marker);
      }
      if (removed.length) cluster.removeLayers(removed);
      if (added.length) cluster.addLayers(added);
      scheduleFit();
    },

    select(detection) {
      const previous = selectedId ? entries.get(selectedId) : undefined;
      if (previous) {
        previous.marker.setIcon(icon(previous.det, false));
        previous.marker.setZIndexOffset(TIER_Z[previous.det.alert_tier as AlertTier]);
      }
      uncertainty?.remove();
      uncertainty = null;
      selectedId = detection?.detection_id ?? null;
      const entry = selectedId ? entries.get(selectedId) : undefined;
      if (!detection || !entry) return;
      entry.marker.setIcon(icon(entry.det, true));
      entry.marker.setZIndexOffset(TIER_Z[entry.det.alert_tier as AlertTier] + 1000);
      const where = located(detection) as LatLon;
      const radius = detection.position.uncertainty_m;
      if (radius && radius > 0) {
        uncertainty = L.circle(where, { radius, className: 'ss-uncertainty', weight: 1, fillOpacity: 0.08 }).addTo(map);
      }
      programmatic = true;
      cluster.zoomToShowLayer(entry.marker, () => map.panTo(where, { animate }));
    },

    zoomToPoints(points) {
      fitTo(points);
    },

    destroy() {
      map.remove();
    },
  };
}
