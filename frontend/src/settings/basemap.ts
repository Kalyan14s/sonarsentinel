import { useEffect, useState } from 'react';

import { api, type Basemap } from '../api/client';

/**
 * Basemap source (ST-099, FR-UI-14): offline tiles from `/api/v1/tiles` when Settings asks for them
 * and the backend has an MBTiles file (`/health` → `offline_tiles`), otherwise OpenStreetMap online.
 * OSM's tile policy forbids bulk download, so offline tiles are rendered by the team (LICENSES §3).
 */
export const ONLINE_TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
export const OFFLINE_TILE_URL = '/api/v1/tiles/{z}/{x}/{y}.png';
export const ONLINE_ATTRIBUTION = '&copy; OpenStreetMap contributors';
export const OFFLINE_ATTRIBUTION = '&copy; OpenStreetMap contributors (offline)';

export interface BasemapState {
  tileUrl: string;
  offline: boolean;
}

export function selectBasemap(preference: Basemap | undefined, offlineTilesAvailable: boolean | undefined): BasemapState {
  const offline = preference === 'offline' && offlineTilesAvailable === true;
  return { tileUrl: offline ? OFFLINE_TILE_URL : ONLINE_TILE_URL, offline };
}

/** Local (same-origin) tile URLs get the offline attribution. */
export function tileAttribution(tileUrl: string): string {
  return tileUrl.startsWith('/') ? OFFLINE_ATTRIBUTION : ONLINE_ATTRIBUTION;
}

let cached: Promise<BasemapState> | null = null;

/** Settings + health, fetched once per page load; any failure means online tiles. */
export function loadBasemap(): Promise<BasemapState> {
  cached ??= Promise.all([api.settings().catch(() => null), api.health().catch(() => null)]).then(
    ([settings, health]) =>
      selectBasemap(settings?.map.basemap, health?.offline_tiles ?? settings?.system.offline_tiles_available),
    () => selectBasemap(undefined, false),
  );
  return cached;
}

/** Forget the cached choice (after saving Settings, and between tests). */
export function resetBasemapCache(): void {
  cached = null;
}

export function useBasemap(): BasemapState & { loaded: boolean } {
  const [state, setState] = useState<BasemapState & { loaded: boolean }>(() => ({
    ...selectBasemap(undefined, false),
    loaded: false,
  }));
  useEffect(() => {
    let active = true;
    void loadBasemap().then((next) => {
      if (active) setState({ ...next, loaded: true });
    });
    return () => {
      active = false;
    };
  }, []);
  return state;
}
