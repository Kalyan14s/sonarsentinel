import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { detectionQueryString } from './api/client';
import { App } from './App';
import { PRIMARY_NAV, SECONDARY_NAV } from './components/AppBar';
import { markerHtml } from './map/markers';
import { CLASS_STYLES, describeDetection } from './tokens';

vi.mock('./map/MapView', async (importOriginal) => {
  const original = await importOriginal<typeof import('./map/MapView')>();
  return { ...original, MapView: () => <div data-testid="map" /> };
});

describe('App shell', () => {
  it('shows the wireframe navigation in order', () => {
    render(
      <MemoryRouter initialEntries={['/upload']}>
        <App />
      </MemoryRouter>,
    );
    const primary = screen.getByRole('navigation', { name: 'Primary' });
    const labels = Array.from(primary.querySelectorAll('a')).map((a) => a.textContent);
    expect(labels).toEqual(['Upload', 'Live Map', 'Review', 'Reports', 'History']);
    expect(SECONDARY_NAV.map((item) => item.label)).toEqual(['Settings', 'Help']);
    expect(screen.getByRole('heading', { name: 'New analysis' })).toBeInTheDocument();
    expect(PRIMARY_NAV).toHaveLength(5);
  });

  it('routes unknown paths to the not-found page', () => {
    render(
      <MemoryRouter initialEntries={['/nope']}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
  });
});

describe('design tokens', () => {
  it('keeps TypeScript class colours in sync with tokens.css', () => {
    const css = readFileSync(resolve(__dirname, 'styles/tokens.css'), 'utf8');
    for (const style of Object.values(CLASS_STYLES)) {
      const match = css.match(new RegExp(`${style.cssVar}:\\s*(#[0-9a-fA-F]{6})`));
      expect(match?.[1]?.toLowerCase()).toBe(style.color);
    }
  });

  it('uses the wireframe colours and shapes', () => {
    expect(CLASS_STYLES.ghost_net).toMatchObject({ color: '#e5484d', shape: 'diamond' });
    expect(CLASS_STYLES.unknown_anomaly.shape).toBe('hexagon');
    expect(markerHtml('pipe', 'hazard')).toContain('ss-bar ss-tier-hazard');
  });

  it('builds screen-reader labels', () => {
    expect(describeDetection('ghost_net', 87.4, 'hazard', 13.08412, 80.31275)).toBe(
      'Ghost net, 87 percent, hazard, 13.084120 north, 80.312750 east',
    );
    expect(describeDetection('pipe', 51, 'review', null, null)).toContain('not geotagged');
  });
});

describe('api client', () => {
  it('encodes detection filters like the API spec', () => {
    expect(detectionQueryString({ class: ['ghost_net', 'pipe'], min_conf: 50, sort: '-confidence' })).toBe(
      '?class=ghost_net%2Cpipe&min_conf=50&sort=-confidence',
    );
    expect(detectionQueryString({})).toBe('');
  });
});
