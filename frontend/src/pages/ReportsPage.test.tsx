import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { json, makeSurvey } from '../test/fixtures';
import { ReportsPage } from './ReportsPage';

const GEOTAGGED = makeSurvey({
  survey_id: 'SRV-20260913-001',
  name: 'Chennai-Port-Line07',
  summary: { total_detections: 7, by_class: {}, by_tier: { hazard: 3, review: 3, anomaly: 1 } },
  report_urls: { csv: '/api/v1/surveys/SRV-20260913-001/report?format=csv' },
});
const IMAGE_ONLY = makeSurvey({
  survey_id: 'SRV-20260913-002',
  name: 'Harbour image',
  bbox: null,
  job: { job_id: 'JOB-2', status: 'running', duration_s: null },
});

function renderReports(entry: string) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/reports" element={<ReportsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const hrefOf = (name: string) => screen.getByRole('link', { name }).getAttribute('href');

describe('S-06 reports and export (ST-095)', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === '/api/v1/surveys') return json({ total: 2, items: [GEOTAGGED, IMAGE_ONLY] });
        if (url.includes('/report?')) return new Response('detection_id,class,confidence\nSRV-20260913-001-D0001,shipwreck,91.2\n');
        return json({ error: { code: 'NOT_FOUND', message: url, details: {} } }, 404);
      }),
    );
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('builds download URLs for every format and scope (TC-UI-008)', async () => {
    renderReports('/reports?survey=SRV-20260913-001');
    expect(await screen.findByRole('heading', { name: 'Reports — Chennai-Port-Line07' })).toBeInTheDocument();
    expect(hrefOf('SRV-20260913-001_report.json')).toBe('/api/v1/surveys/SRV-20260913-001/report?format=json&scope=all');
    expect(hrefOf('SRV-20260913-001_report.csv')).toBe('/api/v1/surveys/SRV-20260913-001/report?format=csv&scope=all');

    fireEvent.click(screen.getByRole('checkbox', { name: /GeoJSON/ }));
    fireEvent.click(screen.getByRole('checkbox', { name: /KML/ }));
    expect(hrefOf('SRV-20260913-001_report.geojson')).toBe('/api/v1/surveys/SRV-20260913-001/report?format=geojson&scope=all');
    expect(hrefOf('SRV-20260913-001_report.kml')).toBe('/api/v1/surveys/SRV-20260913-001/report?format=kml&scope=all');

    fireEvent.click(screen.getByRole('radio', { name: 'Hazards only (3)' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Include rejected detections' }));
    expect(hrefOf('SRV-20260913-001_report.kml')).toBe(
      '/api/v1/surveys/SRV-20260913-001/report?format=kml&scope=hazards&include_rejected=true',
    );

    await waitFor(() => expect(screen.getByLabelText('Report preview')).toHaveTextContent('SRV-20260913-001-D0001,shipwreck,91.2'));
    expect(screen.getByRole('link', { name: 'CSV · all detections' })).toBeInTheDocument();
  });

  it('carries the map filters into the filtered scope', async () => {
    renderReports('/reports?survey=SRV-20260913-001&min_conf=60&tier=hazard,review');
    await screen.findByRole('heading', { name: 'Reports — Chennai-Port-Line07' });
    expect(screen.getByRole('radio', { name: 'Current map filters' })).toBeChecked();
    expect(hrefOf('SRV-20260913-001_report.csv')).toBe(
      '/api/v1/surveys/SRV-20260913-001/report?format=csv&scope=filtered&tier=hazard%2Creview&min_conf=60&max_conf=100',
    );
  });

  it('disables GeoJSON/KML without GPS and marks processing surveys as partial', async () => {
    renderReports('/reports?survey=SRV-20260913-002');
    expect(await screen.findByRole('heading', { name: 'Reports — Harbour image' })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: /GeoJSON/ })).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: /KML/ })).toBeDisabled();
    expect(screen.getByRole('status')).toHaveTextContent('Survey still processing');
    expect(screen.queryByRole('link', { name: /report\.geojson/ })).not.toBeInTheDocument();
  });
});
