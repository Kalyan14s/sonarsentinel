import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Detection, ReviewRequest } from '../api/client';
import { ALL_CLASSES } from '../dashboard/filters';
import { keyAction, nextPendingId, whyText } from '../review/reviewModel';
import { json, makeDetection, makeSurvey } from '../test/fixtures';
import { ReviewPage } from './ReviewPage';

vi.mock('../map/MapView', () => ({ MapView: () => <div data-testid="mini-map" /> }));

const SURVEY_ID = 'SRV-20260913-001';

interface Server {
  patches: { id: string; body: ReviewRequest }[];
  items: Map<string, Detection>;
  failures: number;
}

function mockServer(detections: Detection[], failures = 0): Server {
  const server: Server = { patches: [], items: new Map(detections.map((d) => [d.detection_id, d])), failures };
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input).split('?')[0] ?? '';
      if (init?.method === 'PATCH') {
        const id = decodeURIComponent(path.split('/').pop() ?? '');
        const body = JSON.parse(String(init.body)) as ReviewRequest;
        server.patches.push({ id, body });
        if (server.failures > 0) {
          server.failures -= 1;
          return json({ error: { code: 'INTERNAL_ERROR', message: 'boom', details: {} } }, 500);
        }
        const before = server.items.get(id);
        if (!before) return json({ error: { code: 'NOT_FOUND', message: 'missing', details: {} } }, 404);
        const after: Detection = {
          ...before,
          class: (body.class ?? before.class) as Detection['class'],
          review: {
            ...before.review,
            status: body.review_status,
            reject_reason: body.reject_reason ?? null,
            note: body.note ?? null,
          },
        };
        server.items.set(id, after);
        return json(after);
      }
      if (path === '/api/v1/surveys') return json({ total: 1, items: [makeSurvey()] });
      if (path === `/api/v1/surveys/${SURVEY_ID}/detections`) {
        const items = [...server.items.values()];
        return json({ total: items.length, items });
      }
      return json({ error: { code: 'NOT_FOUND', message: `no route ${path}`, details: {} } }, 404);
    }),
  );
  return server;
}

function renderPage(entry = '/review') {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/review" element={<ReviewPage />} />
        <Route path="/review/:surveyId" element={<ReviewPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const press = (key: string) => act(() => void fireEvent.keyDown(window, { key }));

const pendingItems = (n: number) =>
  Array.from({ length: n }, (_, i) => makeDetection(i + 1, { confidence: 50 + i, alert_tier: 'review' }));

describe('S-05 review queue (ST-096)', () => {
  beforeEach(() => {
    vi.useRealTimers();
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('reviews 20 items with the keyboard only (TC-UI-011, TC-USE-002)', async () => {
    const items = pendingItems(20);
    const server = mockServer(items);
    renderPage();
    expect(await screen.findByText('0 of 20 done')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: /^D1 · / })).toBeInTheDocument();

    const started = performance.now();
    items.forEach((item, i) => {
      if (i % 3 === 0) press('c');
      else if (i % 3 === 1) {
        press('r');
        press('2');
      } else {
        press('k');
        press(String(ALL_CLASSES.findIndex((c) => c !== item.class) + 1));
      }
    });

    await waitFor(() => expect(server.patches).toHaveLength(20));
    expect(performance.now() - started).toBeLessThan(180_000);
    expect(server.patches[0]).toEqual({ id: items[0]!.detection_id, body: { review_status: 'confirmed' } });
    expect(server.patches[1]?.body).toEqual({ review_status: 'rejected', reject_reason: 'shadow' });
    expect(server.patches[2]?.body.review_status).toBe('reclassified');
    expect(server.patches[2]?.body.class).not.toBe(items[2]!.class);
    expect(server.patches.map((p) => p.id)).toEqual(items.map((d) => d.detection_id));

    expect(await screen.findByText('[ok] Review complete')).toBeInTheDocument();
    expect(screen.getByText('20 reviewed: 7 confirmed, 7 rejected, 6 reclassified')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Download updated report' })).toHaveAttribute(
      'href',
      `/api/v1/surveys/${SURVEY_ID}/report?format=csv&scope=all`,
    );
  });

  it('skips, moves and undoes the last decision within 10 s', async () => {
    const server = mockServer(pendingItems(3));
    renderPage(`/review/${SURVEY_ID}`);
    await screen.findByText('0 of 3 done');
    press('n');
    expect(screen.getByRole('heading', { level: 2, name: /^D2 · / })).toBeInTheDocument();
    press('p');
    expect(screen.getByRole('heading', { level: 2, name: /^D1 · / })).toBeInTheDocument();
    press('s');
    expect(screen.getByRole('heading', { level: 2, name: /^D2 · / })).toBeInTheDocument();
    expect(server.patches).toHaveLength(0);

    press('c');
    await waitFor(() => expect(server.patches).toHaveLength(1));
    expect(screen.getByRole('heading', { level: 2, name: /^D3 · / })).toBeInTheDocument();
    press('z');
    await waitFor(() => expect(server.patches).toHaveLength(2));
    expect(server.patches[1]).toEqual({ id: server.patches[0]!.id, body: { review_status: 'pending' } });
    expect(screen.getByRole('heading', { level: 2, name: /^D2 · / })).toBeInTheDocument();
    await screen.findByText('0 of 3 done');
  });

  it('retries a failed save once, then offers Retry', async () => {
    const server = mockServer(pendingItems(2), 2);
    renderPage();
    await screen.findByText('0 of 2 done');
    press('c');
    expect(await screen.findByText('Not saved')).toBeInTheDocument();
    expect(server.patches).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(screen.queryByText('Not saved')).not.toBeInTheDocument());
    expect(server.patches).toHaveLength(3);
  });

  it('shows the empty queue', async () => {
    mockServer([]);
    renderPage();
    expect(await screen.findByText(/Nothing to review/)).toBeInTheDocument();
  });
});

describe('review model', () => {
  it('maps keys by mode', () => {
    expect(keyAction('c', 'idle', 'pipe')).toEqual({ type: 'confirm' });
    expect(keyAction('1', 'reject', 'pipe')).toEqual({ type: 'reason', reason: 'rock' });
    expect(keyAction('5', 'reject', 'pipe')).toEqual({ type: 'reason', reason: 'other' });
    const index = ALL_CLASSES.indexOf('pipe');
    expect(keyAction(String(index + 1), 'reclassify', 'pipe')).toBeNull();
    expect(keyAction('1', 'idle', 'pipe')).toBeNull();
    expect(keyAction('Escape', 'reject', 'pipe')).toEqual({ type: 'cancel' });
  });

  it('finds the next pending item and explains scores', () => {
    const list = pendingItems(3);
    const reviewed = list.map((d, i) => (i === 1 ? { ...d, review: { ...d.review, status: 'confirmed' as const } } : d));
    expect(nextPendingId(reviewed, reviewed[0]!.detection_id)).toBe(reviewed[2]!.detection_id);
    expect(nextPendingId(reviewed, reviewed[2]!.detection_id)).toBe(reviewed[0]!.detection_id);
    expect(whyText(list[0]!)).toMatch(/^Why 50%: detector 0\.81 · shadow 0\.64 · FP filter 0\.88/);
  });
});
