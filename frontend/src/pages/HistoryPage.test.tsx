import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { SurveyListItem } from '../api/client';
import { historyQuery } from '../history/historyModel';
import { json, makeSurvey } from '../test/fixtures';
import { HistoryPage } from './HistoryPage';

function item(overrides: Partial<SurveyListItem>): SurveyListItem {
  return {
    ...makeSurvey(),
    project: 'chennai-port',
    status: 'completed_with_warnings',
    warning_count: 2,
    size_bytes: 1_400_000_000,
    summary: { total_detections: 5, by_class: { ghost_net: 2, pipe: 3 }, by_tier: { hazard: 3, review: 2 } },
    ...overrides,
  };
}

const SURVEYS: SurveyListItem[] = [
  item({}),
  item({
    survey_id: 'SRV-20260910-002',
    name: 'Harbour-03',
    source_files: ['harbour_03.png'],
    status: 'failed',
    error_code: 'CRS_REQUIRED',
    job: { job_id: 'JOB-2', status: 'failed', duration_s: null },
  }),
  item({
    survey_id: 'SRV-20260913-003',
    name: 'Line08',
    status: 'running',
    job: { job_id: 'JOB-3', status: 'running', duration_s: null },
  }),
];

function mockServer(deleteStatus: 204 | 409 = 204) {
  const calls: { method: string; url: string }[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? 'GET';
      calls.push({ method, url });
      if (method === 'DELETE') {
        if (deleteStatus === 409) {
          return json({ error: { code: 'JOB_NOT_CANCELLABLE', message: 'Cancel the job first', details: {} } }, 409);
        }
        return new Response(null, { status: 204 });
      }
      if (url.startsWith('/api/v1/surveys')) return json({ total: SURVEYS.length, items: SURVEYS });
      return json({ error: { code: 'NOT_FOUND', message: 'no route', details: {} } }, 404);
    }),
  );
  return calls;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/history']}>
      <Routes>
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/upload" element={<p>upload page</p>} />
        <Route path="/map/:surveyId" element={<p>map page</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('S-07 survey history (ST-098)', () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('shows rows with status, counts, hazards and the right actions', async () => {
    mockServer();
    renderPage();
    const row = (await screen.findByText('Chennai-Port-Line07')).closest('tr')!;
    expect(within(row).getByText('[ok] Done (!2)')).toBeInTheDocument();
    expect(within(row).getByText('Ghost net 2')).toBeInTheDocument();
    expect(within(row).getByText(/1.3 GB|1.4 GB/)).toBeInTheDocument();
    expect(within(row).getByRole('link', { name: 'Open' })).toHaveAttribute('href', '/map/SRV-20260913-001');

    const failed = screen.getByText('Harbour-03').closest('tr')!;
    expect(within(failed).getByText('CRS_REQUIRED')).toBeInTheDocument();
    expect(within(failed).getByRole('link', { name: 'Fix' }).getAttribute('href')).toContain('code=CRS_REQUIRED');

    const running = screen.getByText('Line08').closest('tr')!;
    expect(within(running).getByRole('link', { name: 'Open' })).toHaveAttribute(
      'href',
      '/map/SRV-20260913-003?job=JOB-3',
    );
  });

  it('maps search and filters to the query', async () => {
    const calls = mockServer();
    renderPage();
    await screen.findByText('Chennai-Port-Line07');
    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'line' } });
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'failed' } });
    await waitFor(() =>
      expect(calls.some((c) => c.url.includes('q=line') && c.url.includes('status=failed'))).toBe(true),
    );
    expect(historyQuery({ q: ' net ', project: 'p1', status: 'queued,running', days: '30' }, new Date('2026-09-14T12:00:00Z'))).toEqual({
      limit: 200,
      q: 'net',
      project: 'p1',
      status: ['queued', 'running'],
      from: '2026-08-15',
    });
  });

  it('deletes after confirmation', async () => {
    const calls = mockServer();
    renderPage();
    await screen.findByText('Chennai-Port-Line07');
    fireEvent.click(screen.getByRole('button', { name: 'More actions for Chennai-Port-Line07' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete' }));
    const dialog = screen.getByRole('alertdialog', { name: 'Delete survey' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(screen.queryByText('Chennai-Port-Line07')).not.toBeInTheDocument());
    expect(calls).toContainEqual({ method: 'DELETE', url: '/api/v1/surveys/SRV-20260913-001' });
    expect(screen.getByRole('status')).toHaveTextContent('Deleted Chennai-Port-Line07');
  });

  it('explains a 409 when the job is still running', async () => {
    mockServer(409);
    renderPage();
    await screen.findByText('Line08');
    fireEvent.click(screen.getByRole('button', { name: 'More actions for Line08' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete' }));
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Delete' }));
    expect(await screen.findByText(/still processing — cancel the job first/)).toBeInTheDocument();
    expect(screen.getByText('Line08')).toBeInTheDocument();
  });
});
