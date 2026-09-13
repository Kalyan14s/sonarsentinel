import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { EditableSettings, Settings } from '../api/client';
import { validateSettings } from '../settings/settingsModel';
import { json } from '../test/fixtures';
import { SettingsPage } from './SettingsPage';

function settings(overrides: Partial<Settings['system']> = {}): Settings {
  return {
    detection: { model_id: 'yolo11s-seg-sonar-real@0.1.0', runtime: 'auto', min_raw_score: 0.2 },
    anomaly: { enabled: true, threshold: 0.5 },
    tiers: { hazard: 80, review: 50, anomaly: 30 },
    map: { min_conf_default: 30, basemap: 'online', coordinates: 'dd' },
    processing: { ground_resolution_m: 0.1, pings_per_chunk: 2000, overlap_pings: 200 },
    geo: { apply_layback: 'auto', cluster_radius_m: 5 },
    system: {
      data_dir: 'data/api',
      max_upload_gb: 2,
      keep_work_files: false,
      offline_tiles_available: false,
      runtimes_available: ['torch', 'onnxruntime'],
      version: '0.3.0',
      ...overrides,
    },
  };
}

function mockServer(putResponse?: Response) {
  const puts: EditableSettings[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input).split('?')[0];
      if (path === '/api/v1/settings' && init?.method === 'PUT') {
        const body = JSON.parse(String(init.body)) as EditableSettings;
        puts.push(body);
        return putResponse ?? json({ ...settings(), ...body });
      }
      if (path === '/api/v1/settings') return json(settings());
      if (path === '/api/v1/models') {
        return json({
          total: 1,
          items: [{ kind: 'detector', id: 'yolo11s-seg-sonar-real@0.1.0', available: true, trained: true }],
        });
      }
      if (path === '/api/v1/health') return json({ status: 'ok', version: '0.3.0', runtime: 'cpu', offline_tiles: false });
      return json({ error: { code: 'NOT_FOUND', message: 'no route', details: {} } }, 404);
    }),
  );
  return puts;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/settings']}>
      <Routes>
        <Route
          path="/settings"
          element={
            <>
              <Link to="/upload">Go to upload</Link>
              <SettingsPage />
            </>
          }
        />
        <Route path="/upload" element={<p>upload page</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('S-07 settings (ST-098)', () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('blocks Save while tiers are out of order', async () => {
    mockServer();
    renderPage();
    const hazard = await screen.findByLabelText('Hazard tier (%)');
    fireEvent.change(hazard, { target: { value: '40' } });
    expect(screen.getByText('Hazard must be higher than Review, and Review higher than Anomaly')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled();
  });

  it('saves only the editable sections', async () => {
    const puts = mockServer();
    renderPage();
    fireEvent.change(await screen.findByLabelText('Hazard tier (%)'), { target: { value: '85' } });
    fireEvent.click(screen.getByRole('checkbox', { name: 'Anomaly scan enabled' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]).not.toHaveProperty('system');
    expect(puts[0]?.tiers).toEqual({ hazard: 85, review: 50, anomaly: 30 });
    expect(puts[0]?.anomaly.enabled).toBe(false);
    expect(await screen.findByText('Settings saved — they apply to new jobs')).toBeInTheDocument();
  });

  it('shows server validation details inline', async () => {
    mockServer(
      json(
        {
          error: {
            code: 'VALIDATION_ERROR',
            message: 'Invalid settings',
            details: { errors: [{ field: 'processing.pings_per_chunk', message: 'Chunk too large for memory' }] },
          },
        },
        400,
      ),
    );
    renderPage();
    fireEvent.change(await screen.findByLabelText('Chunk size (pings)'), { target: { value: '90000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    expect(await screen.findByText('Chunk too large for memory')).toBeInTheDocument();
  });

  it('disables the offline basemap without tiles and lists unavailable runtimes', async () => {
    mockServer();
    renderPage();
    const offline = await screen.findByRole('radio', { name: 'Offline (tiles/basemap.mbtiles)' });
    expect(offline).toBeDisabled();
    expect(screen.getByText('No offline tiles installed on the server')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'TensorRT (unavailable)' })).toBeDisabled();
    expect(screen.getByRole('option', { name: 'ONNX Runtime (CPU)' })).not.toBeDisabled();
  });

  it('asks before leaving with unsaved changes', async () => {
    mockServer();
    renderPage();
    fireEvent.change(await screen.findByLabelText('Cluster radius (m)'), { target: { value: '8' } });
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
    fireEvent.click(screen.getByRole('link', { name: 'Go to upload' }));
    expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('link', { name: 'Go to upload' }));
    expect(await screen.findByText('upload page')).toBeInTheDocument();
    expect(confirm).toHaveBeenCalledTimes(2);
  });

  it('validates offline basemap against the server tiles', () => {
    const s = settings();
    expect(validateSettings({ ...s, map: { ...s.map, basemap: 'offline' } }, s.system)).toHaveProperty('map.basemap');
    expect(validateSettings(s, s.system)).toEqual({});
  });
});
