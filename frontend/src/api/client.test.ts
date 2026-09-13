import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { FakeWebSocket } from '../test/fakeWebSocket';
import { makeDetection } from '../test/fixtures';
import { api, reportQueryString, subscribeToJob, type ConnectionStatus, type JobEvent } from './client';

const Impl = FakeWebSocket as unknown as typeof WebSocket;

describe('subscribeToJob', () => {
  beforeEach(() => {
    FakeWebSocket.reset();
    vi.useFakeTimers();
  });
  afterEach(() => vi.useRealTimers());

  it('resumes after a dropped connection without duplicates (TC-UI-014, TC-WS-004)', () => {
    const events: JobEvent[] = [];
    const statuses: ConnectionStatus[] = [];
    const stop = subscribeToJob('JOB-1', (e) => events.push(e), {
      WebSocketImpl: Impl,
      baseUrl: 'ws://test',
      onStatus: (s) => statuses.push(s),
    });
    const first = FakeWebSocket.last();
    expect(first.url).toBe('ws://test/ws/jobs/JOB-1');
    first.open();
    expect(first.sent).toEqual([{ type: 'resume', after_seq: 0 }]);
    first.emit({ type: 'progress', seq: 1, stage: 'detect', percent: 20 });
    first.emit({ type: 'detection', seq: 2, detection: makeDetection(1) });
    first.drop(1006);
    expect(statuses).toEqual(['connecting', 'live', 'reconnecting']);

    vi.advanceTimersByTime(500);
    const second = FakeWebSocket.last();
    expect(second).not.toBe(first);
    second.open();
    expect(second.sent[0]).toEqual({ type: 'resume', after_seq: 2 });
    second.emit({ type: 'detection', seq: 2, detection: makeDetection(1) });
    second.emit({ type: 'pong' });
    second.emit({ type: 'detection', seq: 3, detection: makeDetection(2) });
    expect(events.map((e) => e.seq)).toEqual([1, 2, 3]);

    second.emit({ type: 'done', seq: 4, status: 'completed', summary: { total_detections: 2, by_class: {}, by_tier: {} } });
    second.drop(1000);
    vi.advanceTimersByTime(30_000);
    expect(FakeWebSocket.instances).toHaveLength(2);
    expect(statuses[statuses.length - 1]).toBe('closed');
    stop();
  });

  it('pings every 20 s and stops for an unknown job (4404)', () => {
    const statuses: ConnectionStatus[] = [];
    subscribeToJob('JOB-X', () => undefined, { WebSocketImpl: Impl, baseUrl: 'ws://t', onStatus: (s) => statuses.push(s) });
    const socket = FakeWebSocket.last();
    socket.open();
    vi.advanceTimersByTime(40_000);
    expect(socket.sent.filter((m) => m.type === 'ping')).toHaveLength(2);
    socket.drop(4404);
    vi.advanceTimersByTime(30_000);
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(statuses[statuses.length - 1]).toBe('closed');
  });

  it('backs off exponentially up to 10 s', () => {
    subscribeToJob('JOB-2', () => undefined, { WebSocketImpl: Impl, baseUrl: 'ws://t' });
    const delays = [500, 1000, 2000, 4000, 8000, 10_000, 10_000];
    for (const delay of delays) {
      const count = FakeWebSocket.instances.length;
      FakeWebSocket.last().drop(1006);
      vi.advanceTimersByTime(delay - 1);
      expect(FakeWebSocket.instances).toHaveLength(count);
      vi.advanceTimersByTime(1);
      expect(FakeWebSocket.instances).toHaveLength(count + 1);
    }
  });

  it('does not reconnect after unsubscribe', () => {
    const stop = subscribeToJob('JOB-3', () => undefined, { WebSocketImpl: Impl, baseUrl: 'ws://t' });
    FakeWebSocket.last().open();
    stop();
    FakeWebSocket.last().drop(1006);
    vi.advanceTimersByTime(30_000);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });
});

describe('report and chip URLs (TC-UI-008 part)', () => {
  it('encodes format, scope, filters and rejected option', () => {
    expect(api.reportUrl('SRV-1', 'csv')).toBe('/api/v1/surveys/SRV-1/report?format=csv&scope=all');
    expect(
      reportQueryString('geojson', {
        scope: 'filtered',
        includeRejected: true,
        filters: { tier: ['hazard', 'review'], min_conf: 60, max_conf: 100 },
      }),
    ).toBe('?format=geojson&scope=filtered&tier=hazard%2Creview&min_conf=60&max_conf=100&include_rejected=true');
    expect(reportQueryString('kml', { scope: 'hazards', filters: { min_conf: 60 } })).toBe('?format=kml&scope=hazards');
    expect(api.chipUrl('SRV-1-D0001', 'shadow')).toBe('/api/v1/detections/SRV-1-D0001/chip.png?overlay=shadow');
  });
});
