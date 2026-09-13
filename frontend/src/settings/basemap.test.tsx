import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AppBar } from '../components/AppBar';
import { json } from '../test/fixtures';
import {
  OFFLINE_ATTRIBUTION,
  OFFLINE_TILE_URL,
  ONLINE_ATTRIBUTION,
  ONLINE_TILE_URL,
  resetBasemapCache,
  selectBasemap,
  tileAttribution,
} from './basemap';

function mockServer(basemap: 'online' | 'offline', offlineTiles: boolean) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path === '/api/v1/settings') return json({ map: { basemap }, system: { offline_tiles_available: offlineTiles } });
      if (path === '/api/v1/health') return json({ status: 'ok', version: '0.3.0', runtime: 'cpu', offline_tiles: offlineTiles });
      return json({}, 404);
    }),
  );
}

describe('offline basemap (ST-099)', () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    resetBasemapCache();
  });

  it('uses local tiles only when chosen and installed', () => {
    expect(selectBasemap('offline', true)).toEqual({ tileUrl: OFFLINE_TILE_URL, offline: true });
    expect(selectBasemap('offline', false)).toEqual({ tileUrl: ONLINE_TILE_URL, offline: false });
    expect(selectBasemap('online', true)).toEqual({ tileUrl: ONLINE_TILE_URL, offline: false });
    expect(selectBasemap(undefined, undefined).offline).toBe(false);
    expect(tileAttribution(OFFLINE_TILE_URL)).toBe(OFFLINE_ATTRIBUTION);
    expect(tileAttribution(ONLINE_TILE_URL)).toBe(ONLINE_ATTRIBUTION);
  });

  it('shows the offline badge when local tiles are active', async () => {
    mockServer('offline', true);
    render(
      <MemoryRouter>
        <AppBar />
      </MemoryRouter>,
    );
    expect(await screen.findByRole('status')).toHaveTextContent('Offline — local tiles');
  });

  it('hides the badge when tiles are missing', async () => {
    mockServer('offline', false);
    render(
      <MemoryRouter>
        <AppBar />
      </MemoryRouter>,
    );
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.queryByText('Offline — local tiles')).not.toBeInTheDocument();
  });
});
