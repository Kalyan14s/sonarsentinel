import L from 'leaflet';
import { useEffect, useRef } from 'react';

import type { Detection } from '../api/client';
import { describeDetection, TIER_Z, type AlertTier, type DetectionClass } from '../tokens';
import { markerHtml } from './markers';
import styles from './MapView.module.css';

interface MapViewProps {
  track: [number, number][]; // [lat, lon]
  detections: Detection[];
  selectedId?: string | null;
  onSelect?: (id: string) => void;
  tileUrl?: string;
}

const DEFAULT_TILES = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';

/**
 * Thin React wrapper around Leaflet, used directly as decided in ADR-009 (no react-leaflet).
 * Offline MBTiles support replaces `tileUrl` in ST-099.
 */
export function MapView({ track, detections, selectedId, onSelect, tileUrl = DEFAULT_TILES }: MapViewProps) {
  const element = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layers = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    if (!element.current || map.current) return;
    map.current = L.map(element.current, { preferCanvas: false }).setView([13.08, 80.3], 13);
    L.tileLayer(tileUrl, { maxZoom: 20, attribution: '&copy; OpenStreetMap contributors' }).addTo(map.current);
    layers.current = L.layerGroup().addTo(map.current);
    return () => {
      map.current?.remove();
      map.current = null;
    };
  }, [tileUrl]);

  useEffect(() => {
    const group = layers.current;
    const leaflet = map.current;
    if (!group || !leaflet) return;
    group.clearLayers();
    if (track.length > 1) {
      L.polyline(track, { color: 'var(--color-track)', weight: 3 }).addTo(group);
    }
    const bounds: L.LatLngTuple[] = [...track];
    for (const det of detections) {
      const { lat, lon } = det.position;
      if (lat === null || lon === null) continue;
      const cls = det.class as DetectionClass;
      const tier = det.alert_tier as AlertTier;
      const marker = L.marker([lat, lon], {
        icon: L.divIcon({ className: '', html: markerHtml(cls, tier), iconSize: [22, 22] }),
        keyboard: true,
        title: describeDetection(cls, det.confidence, tier, lat, lon),
        alt: describeDetection(cls, det.confidence, tier, lat, lon),
        zIndexOffset: TIER_Z[tier] + (det.detection_id === selectedId ? 1000 : 0),
        opacity: tier === 'hidden' ? 0.5 : 1,
      });
      marker.on('click', () => onSelect?.(det.detection_id));
      marker.addTo(group);
      bounds.push([lat, lon]);
    }
    if (bounds.length) leaflet.fitBounds(L.latLngBounds(bounds), { padding: [32, 32], maxZoom: 18 });
  }, [track, detections, selectedId, onSelect]);

  return <div ref={element} className={styles.map} role="region" aria-label="Survey map" />;
}
