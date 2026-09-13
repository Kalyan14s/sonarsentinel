import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { useEffect } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Detection } from '../api/client';
import { FakeWebSocket } from '../test/fakeWebSocket';
import { json, makeDetection, makeSurvey } from '../test/fixtures';
import { LiveMapPage } from './LiveMapPage';

const controller = vi.hoisted(() => ({
  setTrack: vi.fn(),
  setQualitySegments: vi.fn(),
  setMosaic: vi.fn(),
  setDetections: vi.fn(),
  select: vi.fn(),
  zoomToPoints: vi.fn(),
  destroy: vi.fn(),
}));

vi.mock('../map/MapView', () => ({
  MapView: (props: {
    track: unknown[];
    quality: unknown[];
    mosaic?: { url: string } | null;
    detections: unknown[];
    onReady?: (c: typeof controller | null) => void;
  }) => {
    const { onReady } = props;
    useEffect(() => {
      onReady?.(controller);
      return () => onReady?.(null);
    }, [onReady]);
    return (
      <div
        data-testid="map"
        data-track={props.track.length}
        data-quality={props.quality.length}
        data-markers={props.detections.length}
        data-mosaic={props.mosaic?.url ?? ''}
      />
    );
  },
}));

const SURVEY_ID = 'SRV-20260913-001';

function mockApi(routes: Record<string, unknown>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const path = url.split('?')[0] ?? url;
    if (path in routes) return json(routes[path]);
    return json({ error: { code: 'NOT_FOUND', message: `no route ${path}`, details: {} } }, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function renderPage(entry: string) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/map/:surveyId" element={<LiveMapPage />} />
        <Route path="/review" element={<p>review</p>} />
        <Route path="/reports" element={<p>reports</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

async function liveSocket(): Promise<FakeWebSocket> {
  await waitFor(() => expect(FakeWebSocket.instances.length).toBeGreaterThan(0));
  const socket = FakeWebSocket.last();
  act(() => socket.open());
  return socket;
}

const detection = (i: number, confidence: number, extra: Partial<Detection> = {}) =>
  makeDetection(i, { confidence, alert_tier: confidence >= 80 ? 'hazard' : 'review', ...extra });

const listRows = () => within(screen.getByRole('listbox', { name: 'Detections' })).getAllByRole('option');

describe('S-02 live map (ST-092/093)', () => {
  beforeEach(() => {
    FakeWebSocket.reset();
    vi.stubGlobal('WebSocket', FakeWebSocket);
    Object.values(controller).forEach((fn) => fn.mockClear());
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('shows the mosaic from the done event (ST-036)', async () => {
    mockApi({
      [`/api/v1/surveys/${SURVEY_ID}`]: makeSurvey({ job: { job_id: 'JOB-1', status: 'running', duration_s: null } }),
    });
    renderPage(`/map/${SURVEY_ID}?job=JOB-1`);
    const socket = await liveSocket();
    act(() => socket.emit({ type: 'track', seq: 1, ping_start: 0, ping_end: 100, points: [[13.08, 80.3], [13.081, 80.301]] }));
    expect(screen.getByTestId('map')).toHaveAttribute('data-mosaic', '');
    const url = `/api/v1/surveys/${SURVEY_ID}/mosaic.png`;
    act(() =>
      socket.emit({
        type: 'done',
        seq: 2,
        status: 'completed',
        summary: { total_detections: 0, by_class: {}, by_tier: {} },
        report_urls: {},
        mosaic: { url, bounds: [[13.08, 80.3], [13.09, 80.31]] },
      }),
    );
    await waitFor(() => expect(screen.getByTestId('map')).toHaveAttribute('data-mosaic', url));
  });

  it('grows the track and streams markers and counts (TC-UI-003, TC-WS-005)', async () => {
    mockApi({
      [`/api/v1/surveys/${SURVEY_ID}`]: makeSurvey({ job: { job_id: 'JOB-1', status: 'running', duration_s: null } }),
    });
    renderPage(`/map/${SURVEY_ID}?job=JOB-1`);
    const socket = await liveSocket();
    expect(socket.sent[0]).toEqual({ type: 'resume', after_seq: 0 });

    act(() => socket.emit({ type: 'progress', seq: 1, stage: 'detect', percent: 46, eta_s: 22, pings_total: 18240 }));
    expect(screen.getByText('No detections yet — scanning 18,240 pings')).toBeInTheDocument();
    expect(screen.getByText(/46% · detect · ETA 00:22/)).toBeInTheDocument();

    act(() => socket.emit({ type: 'track', seq: 2, ping_start: 0, ping_end: 100, points: [[13.08, 80.3], [13.081, 80.301]] }));
    expect(screen.getByTestId('map')).toHaveAttribute('data-track', '2');
    act(() => socket.emit({ type: 'track', seq: 3, ping_start: 100, ping_end: 200, points: [[13.082, 80.302], [13.083, 80.303]] }));
    expect(screen.getByTestId('map')).toHaveAttribute('data-track', '4');

    act(() => {
      socket.emit({ type: 'detection', seq: 4, detection: detection(1, 91) });
      socket.emit({ type: 'detection', seq: 5, detection: detection(2, 62) });
    });
    expect(screen.getByRole('heading', { name: 'Detections (2)' })).toBeInTheDocument();
    expect(screen.getByTestId('map')).toHaveAttribute('data-markers', '2');
    expect(screen.getByText('2 detections: 1 hazard, 1 review, 0 anomaly')).toBeInTheDocument();

    act(() => {
      socket.emit({ type: 'detection_update', seq: 6, detection: { ...detection(1, 93), n_views: 2 } });
      socket.emit({ type: 'detection_removed', seq: 7, detection_id: detection(2, 62).detection_id, merged_into: detection(1, 93).detection_id });
    });
    expect(screen.getByRole('heading', { name: 'Detections (1)' })).toBeInTheDocument();
    expect(screen.getByText('93.0%')).toBeInTheDocument();
  });

  it('zooms to a warning segment when clicked (TC-UI-007)', async () => {
    mockApi({ [`/api/v1/surveys/${SURVEY_ID}`]: makeSurvey({ job: { job_id: 'JOB-1', status: 'running', duration_s: null } }) });
    renderPage(`/map/${SURVEY_ID}?job=JOB-1`);
    const socket = await liveSocket();
    act(() => {
      socket.emit({
        type: 'track',
        seq: 1,
        ping_start: 0,
        ping_end: 400,
        points: [[13.0, 80.0], [13.1, 80.1], [13.2, 80.2], [13.3, 80.3], [13.4, 80.4]],
      });
      socket.emit({ type: 'warning', seq: 2, code: 'DROPOUT', message: 'DROPOUT pings', ping_start: 100, ping_end: 200 });
    });
    expect(screen.getByTestId('map')).toHaveAttribute('data-quality', '1');
    fireEvent.click(screen.getByRole('button', { name: '[!] 1 warning' }));
    fireEvent.click(within(screen.getByRole('list', { name: 'Warnings' })).getByRole('button', { name: 'DROPOUT · pings 100–200' }));
    expect(controller.zoomToPoints).toHaveBeenCalledWith([[13.1, 80.1], [13.2, 80.2]]);
  });

  it('shows "Reconnecting…" and resumes without duplicate markers (TC-UI-014)', async () => {
    mockApi({ [`/api/v1/surveys/${SURVEY_ID}`]: makeSurvey({ job: { job_id: 'JOB-1', status: 'running', duration_s: null } }) });
    renderPage(`/map/${SURVEY_ID}?job=JOB-1`);
    const first = await liveSocket();
    act(() => {
      first.emit({ type: 'detection', seq: 1, detection: detection(1, 85) });
      first.emit({ type: 'detection', seq: 2, detection: detection(2, 70) });
    });
    act(() => first.drop(1006));
    expect(screen.getByText('Reconnecting…')).toBeInTheDocument();

    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(2), { timeout: 2000 });
    const second = FakeWebSocket.last();
    act(() => second.open());
    expect(second.sent[0]).toEqual({ type: 'resume', after_seq: 2 });
    act(() => {
      second.emit({ type: 'detection', seq: 2, detection: detection(2, 70) });
      second.emit({ type: 'detection', seq: 3, detection: detection(3, 88) });
    });
    expect(screen.queryByText('Reconnecting…')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Detections (3)' })).toBeInTheDocument();
    expect(screen.getByTestId('map')).toHaveAttribute('data-markers', '3');
  });

  it('asks before stopping and calls cancel', async () => {
    const fetchMock = mockApi({
      [`/api/v1/surveys/${SURVEY_ID}`]: makeSurvey({ job: { job_id: 'JOB-1', status: 'running', duration_s: null } }),
      '/api/v1/jobs/JOB-1/cancel': { job_id: 'JOB-1', status: 'cancelling' },
    });
    renderPage(`/map/${SURVEY_ID}?job=JOB-1`);
    const socket = await liveSocket();
    act(() => socket.emit({ type: 'progress', seq: 1, stage: 'detect', percent: 10 }));
    fireEvent.click(screen.getByRole('button', { name: 'Stop' }));
    expect(screen.getByRole('alertdialog')).toHaveTextContent('Stop processing? Detections found so far are kept.');
    fireEvent.click(screen.getByRole('button', { name: 'Stop processing' }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('/api/v1/jobs/JOB-1/cancel', expect.objectContaining({ method: 'POST' })),
    );
  });

  it('filters with the slider and moves the selection with the keyboard (TC-UI-004, S-02 keys)', async () => {
    const items = [detection(1, 95), detection(2, 72), detection(3, 55)];
    mockApi({
      [`/api/v1/surveys/${SURVEY_ID}`]: makeSurvey(),
      [`/api/v1/surveys/${SURVEY_ID}/track`]: { type: 'FeatureCollection', features: [] },
      [`/api/v1/surveys/${SURVEY_ID}/detections`]: { total: 3, items },
    });
    renderPage(`/map/${SURVEY_ID}`);
    expect(await screen.findByRole('heading', { name: 'Detections (3)' })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Minimum confidence'), { target: { value: '70' } });
    expect(screen.getByRole('heading', { name: 'Detections (2)' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Minimum confidence'), { target: { value: '30' } });

    fireEvent.keyDown(window, { key: 'ArrowDown' });
    expect(listRows()[0]).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(window, { key: 'ArrowDown' });
    expect(listRows()[1]).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(window, { key: 'Enter' });
    expect(screen.getByRole('region', { name: 'Detection detail' })).toHaveTextContent('72.0%');
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('region', { name: 'Detection detail' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Detections (3)' })).toBeInTheDocument();
  });

  it('shows the pixel view and no coordinates for a survey without GPS (TC-UI-009)', async () => {
    const items = [
      makeDetection(1, {
        confidence: 64,
        alert_tier: 'review',
        position: { lat: null, lon: null, depth_m: null, uncertainty_m: null },
        quality_flags: ['NOT_GEOTAGGED'],
        sonar_ref: { source_file: 'harbour_03.png', side: 'n/a', pixel_bbox: [1204, 830, 1266, 861] },
      }),
    ];
    mockApi({
      [`/api/v1/surveys/${SURVEY_ID}`]: makeSurvey({ bbox: null, source_files: ['harbour_03.png'] }),
      [`/api/v1/surveys/${SURVEY_ID}/detections`]: { total: 1, items },
    });
    renderPage(`/map/${SURVEY_ID}`);
    expect(await screen.findByText('No GPS — coordinates shown in pixels')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Pixel view of 1 detections' })).toBeInTheDocument();
    expect(screen.queryByTestId('map')).not.toBeInTheDocument();
    expect(screen.getByText('pixel x 1204–1266, y 830–861')).toBeInTheDocument();
    expect(screen.queryByText(/13\.0\d{5}/)).not.toBeInTheDocument();
    expect(screen.getByText('GeoJSON')).toHaveAttribute('aria-disabled', 'true');
  });
});
