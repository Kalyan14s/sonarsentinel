import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ValidatedFile } from '../api/client';
import {
  DEFAULT_OPTIONS,
  formatBytes,
  localFileProblem,
  missingNavColumns,
  NAV_TEMPLATE_COLUMNS,
  navTemplateCsv,
  startBlockers,
  toSurveyOptions,
  type FileRow,
} from '../upload/uploadModel';
import { UploadPage } from './UploadPage';

const XTF: ValidatedFile = {
  filename: 'line_07.xtf',
  valid: true,
  format: 'xtf',
  size_bytes: 1503238553,
  sonar: { make: 'Klein', model: '3900', channels: 2 },
  pings: 18240,
  has_navigation: true,
  nav_units: 'latlon',
  warnings: [],
};

const PNG: ValidatedFile = {
  filename: 'harbour_03.png',
  valid: true,
  format: 'image_only',
  size_bytes: 2048,
  width: 3200,
  height: 1600,
  has_navigation: false,
  warnings: ['NO_NAVIGATION: attach a navigation CSV or continue without GPS'],
};

function LocationProbe() {
  const location = useLocation();
  return <p data-testid="location">{`${location.pathname}${location.search}`}</p>;
}

function renderUpload() {
  return render(
    <MemoryRouter initialEntries={['/upload']}>
      <Routes>
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/map/:surveyId" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

function makeFile(name: string, size = 1024): File {
  const file = new File(['x'], name);
  Object.defineProperty(file, 'size', { value: size });
  return file;
}

function chooseFiles(files: File[]) {
  const input = screen.getByLabelText('Choose sonar files');
  Object.defineProperty(input, 'files', { value: files, configurable: true });
  fireEvent.change(input);
}

/** Mock fetch: `/models` returns nothing, `/surveys/validate` answers per filename. */
function mockApi(results: Record<string, ValidatedFile>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith('/models')) return json({ total: 0, items: [] });
    if (url.endsWith('/surveys/validate')) {
      const file = (init?.body as FormData).get('files') as File;
      const result = results[file.name];
      return result ? json({ files: [result] }) : json({ error: { code: 'UNSUPPORTED_FORMAT', message: 'nope', details: {} } }, 415);
    }
    return json({}, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

const validateCalls = (fetchMock: ReturnType<typeof vi.fn>) =>
  fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/surveys/validate'));

class FakeXhr {
  static last: FakeXhr | null = null;
  upload: { onprogress: ((event: { lengthComputable: boolean; loaded: number; total: number }) => void) | null } = {
    onprogress: null,
  };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  status = 0;
  statusText = '';
  responseText = '';
  method = '';
  url = '';
  body: FormData | null = null;

  constructor() {
    FakeXhr.last = this;
  }

  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }

  send(body: FormData) {
    this.body = body;
  }

  abort() {
    this.onabort?.();
  }
}

beforeEach(() => {
  window.localStorage.clear();
  FakeXhr.last = null;
});

afterEach(() => {
  cleanup(); // vitest globals are off, so Testing Library does not unmount between tests itself
  vi.unstubAllGlobals();
});

describe('UploadPage (S-01)', () => {
  it('starts empty with Start analysis disabled', () => {
    mockApi({});
    renderUpload();
    expect(screen.getByRole('heading', { name: 'New analysis' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Start analysis' })).toBeDisabled();
    expect(screen.getByText('Add at least one supported sonar file.')).toBeInTheDocument();
    expect(screen.queryAllByTestId('file-row')).toHaveLength(0);
  });

  it('validates files and shows rows with badges', async () => {
    const fetchMock = mockApi({ 'line_07.xtf': XTF });
    renderUpload();
    chooseFiles([makeFile('line_07.xtf', 1503238553)]);

    expect(screen.getByText('Reading header…')).toBeInTheDocument();
    expect(await screen.findByText('GPS found')).toBeInTheDocument();
    expect(screen.getByText('1.4 GB')).toBeInTheDocument();
    expect(screen.getByText('XTF · Klein 3900 · 2 ch · 18,240 pings')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Start analysis' })).toBeEnabled();
    expect(validateCalls(fetchMock)).toHaveLength(1);
  });

  it('shows unsupported and too-large files as error rows without calling the API', async () => {
    const fetchMock = mockApi({});
    renderUpload();
    chooseFiles([makeFile('scan.bmp'), makeFile('huge.xtf', 2.6 * 1024 ** 3)]);

    expect(await screen.findByText('.bmp is not supported — use .xtf, .tif, .png, .jpg')).toBeInTheDocument();
    expect(screen.getByText('Unsupported')).toBeInTheDocument();
    expect(screen.getByText('2.6 GB exceeds the 2 GB limit (change in Settings)')).toBeInTheDocument();
    expect(screen.getByText('Too large')).toBeInTheDocument();
    expect(validateCalls(fetchMock)).toHaveLength(0);
    expect(screen.getByRole('button', { name: 'Start analysis' })).toBeDisabled();
  });

  it('blocks Start for an image without GPS until Continue without GPS', async () => {
    mockApi({ 'harbour_03.png': PNG });
    renderUpload();
    chooseFiles([makeFile('harbour_03.png', 2048)]);

    expect(await screen.findByText('No GPS')).toBeInTheDocument();
    expect(screen.getByText('Image · 3200 × 1600 px')).toBeInTheDocument();
    const start = screen.getByRole('button', { name: 'Start analysis' });
    expect(start).toBeDisabled();
    expect(screen.getByText('Attach a navigation CSV or choose Continue without GPS.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Continue without GPS' }));
    expect(start).toBeEnabled();
    expect(screen.getByText('Results will have pixel coordinates only.')).toBeInTheDocument();
  });

  it('shows a server-offline banner and retries', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith('/models')) return json({ total: 0, items: [] });
      throw new TypeError('Failed to fetch');
    });
    vi.stubGlobal('fetch', fetchMock);
    renderUpload();
    chooseFiles([makeFile('line_07.xtf')]);

    expect(await screen.findByText('Backend not reachable — check that the service is running.')).toBeInTheDocument();
    expect(screen.getByText('Not checked (backend offline)')).toBeInTheDocument();

    mockApi({ 'line_07.xtf': XTF });
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('GPS found')).toBeInTheDocument();
    expect(screen.queryByText('Backend not reachable — check that the service is running.')).not.toBeInTheDocument();
  });

  it('uploads with progress and opens the live map with the job id', async () => {
    mockApi({ 'line_07.xtf': XTF });
    vi.stubGlobal('XMLHttpRequest', FakeXhr);
    renderUpload();
    chooseFiles([makeFile('line_07.xtf', 1024)]);
    await screen.findByText('GPS found');

    fireEvent.click(screen.getByRole('button', { name: 'Start analysis' }));
    const xhr = FakeXhr.last;
    expect(xhr).not.toBeNull();
    expect(xhr?.method).toBe('POST');
    expect(xhr?.url).toBe('/api/v1/surveys');
    const sent = JSON.parse(String(xhr?.body?.get('options')));
    expect(sent).toMatchObject({ utm_epsg: 'auto', allow_no_gps: false, apply_layback: 'auto', anomaly_scan: true });
    expect((xhr?.body?.getAll('files') as File[]).map((f) => f.name)).toEqual(['line_07.xtf']);

    act(() => xhr?.upload.onprogress?.({ lengthComputable: true, loaded: 512, total: 1024 }));
    expect(screen.getByText('512 B of 1.0 KB')).toBeInTheDocument();
    expect(screen.getByLabelText('Upload progress for line_07.xtf')).toHaveAttribute('value', '0.5');

    act(() => {
      if (!xhr) return;
      xhr.status = 202;
      xhr.responseText = JSON.stringify({
        survey_id: 'SRV-20260913-001',
        job_id: 'JOB-20260913-001',
        status: 'queued',
        ws_url: '/ws/jobs/JOB-20260913-001',
      });
      xhr.onload?.();
    });
    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent('/map/SRV-20260913-001?job=JOB-20260913-001&min_conf=30'),
    );
  });
});

describe('upload model', () => {
  const row = (patch: Partial<FileRow>): FileRow => ({ id: 1, file: makeFile('a.xtf'), status: 'done', ...patch });

  it('formats sizes and checks files locally', () => {
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(8321002)).toBe('7.9 MB');
    expect(localFileProblem({ name: 'x.XTF', size: 10 })).toBeNull();
    expect(localFileProblem({ name: 'README', size: 10 })?.code).toBe('UNSUPPORTED_FORMAT');
  });

  it('maps advanced options to the API options JSON', () => {
    const options = {
      ...DEFAULT_OPTIONS,
      name: ' Line 07 ',
      coordinates: 'utm' as const,
      utmEpsg: '32644',
      layback: 'manual' as const,
      manualLaybackM: 12.5,
      detectorModel: 'yolo:0.1.0',
    };
    expect(toSurveyOptions(options, true)).toEqual({
      name: 'Line 07',
      utm_epsg: 32644,
      ground_resolution_m: 0.1,
      apply_layback: 'true',
      manual_layback_m: 12.5,
      anomaly_scan: true,
      image_layout: 'port_stbd',
      allow_no_gps: true,
      detector_model: 'yolo:0.1.0',
    });
    expect(toSurveyOptions({ ...DEFAULT_OPTIONS, layback: 'off' }, false)).toMatchObject({
      utm_epsg: 'auto',
      apply_layback: 'false',
      manual_layback_m: null,
    });
  });

  it('checks navigation CSV columns like the backend reader', () => {
    expect(missingNavColumns(['ping', 'lat', 'lon', 'slant_range_m'])).toEqual([]);
    expect(missingNavColumns(['ping', 'easting', 'northing', 'slant_range_m'])).toEqual([]);
    expect(missingNavColumns([`${String.fromCharCode(0xfeff)}ping`, 'lat'])).toEqual(['slant_range_m', 'lon']);
    expect(navTemplateCsv().split('\n')[0]).toBe(NAV_TEMPLATE_COLUMNS.join(','));
    expect(missingNavColumns(navTemplateCsv().split('\n')[0]?.split(',') ?? [])).toEqual([]);
  });

  it('lists start blockers', () => {
    const noGps = row({ result: { ...PNG } });
    expect(startBlockers([], false, false, false)).toEqual(['Add at least one supported sonar file.']);
    expect(startBlockers([noGps], false, false, false)).toEqual([
      'Attach a navigation CSV or choose Continue without GPS.',
    ]);
    expect(startBlockers([noGps], true, false, false)).toEqual([]);
    expect(startBlockers([row({ result: XTF })], false, false, true)).toEqual([
      'Choose a UTM zone (EPSG code) for projected coordinates.',
    ]);
  });
});
