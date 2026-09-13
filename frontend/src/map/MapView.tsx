import { useEffect, useRef } from 'react';

import type { Detection } from '../api/client';
import {
  createMapController,
  type LatLon,
  type MapController,
  type MosaicOverlay,
  type QualitySegment,
} from './mapController';
import styles from './MapView.module.css';

export type { LatLon, MapController, MosaicOverlay, QualitySegment } from './mapController';

interface MapViewProps {
  track: LatLon[];
  quality: QualitySegment[];
  mosaic?: MosaicOverlay | null;
  detections: readonly Detection[];
  selected: Detection | null;
  onSelect?: (id: string) => void;
  onReady?: (controller: MapController | null) => void;
  tileUrl?: string;
}

/**
 * Thin React wrapper around Leaflet, used directly as decided in ADR-009 (no react-leaflet).
 * Offline MBTiles support replaces `tileUrl` in ST-099.
 */
export function MapView({
  track,
  quality,
  mosaic = null,
  detections,
  selected,
  onSelect,
  onReady,
  tileUrl,
}: MapViewProps) {
  const element = useRef<HTMLDivElement>(null);
  const controller = useRef<MapController | null>(null);
  const callbacks = useRef({ onSelect, onReady });

  useEffect(() => {
    callbacks.current = { onSelect, onReady };
  }, [onSelect, onReady]);

  useEffect(() => {
    if (!element.current) return;
    const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
    const created = createMapController(element.current, {
      tileUrl,
      reducedMotion,
      onSelect: (id) => callbacks.current.onSelect?.(id),
    });
    controller.current = created;
    callbacks.current.onReady?.(created);
    return () => {
      callbacks.current.onReady?.(null);
      created.destroy();
      controller.current = null;
    };
  }, [tileUrl]);

  useEffect(() => controller.current?.setTrack(track), [track]);
  useEffect(() => controller.current?.setQualitySegments(quality), [quality]);
  useEffect(() => controller.current?.setMosaic(mosaic), [mosaic]);
  useEffect(() => controller.current?.setDetections(detections), [detections]);
  useEffect(() => controller.current?.select(selected), [selected]);

  return <div ref={element} className={styles.map} role="region" aria-label="Survey map" />;
}
