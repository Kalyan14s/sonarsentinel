import { describe, expect, it } from 'vitest';

import type { JobEvent } from '../api/client';
import { makeDetection } from '../test/fixtures';
import {
  INITIAL_STATE,
  liveReducer,
  pointsForPings,
  qualitySegmentsOf,
  type LiveState,
} from './store';

const apply = (state: LiveState, ...events: JobEvent[]) =>
  events.reduce((s, event) => liveReducer(s, { type: 'event', event }), state);

describe('live survey store', () => {
  it('dedupes replayed events and updates detections in place (TC-UI-014)', () => {
    const d1 = makeDetection(1, { confidence: 60 });
    let state = apply(
      INITIAL_STATE,
      { type: 'detection', seq: 1, detection: d1 },
      { type: 'detection', seq: 1, detection: d1 },
      { type: 'detection_update', seq: 2, detection: { ...d1, confidence: 75, n_views: 2 } },
    );
    expect(state.detections.size).toBe(1);
    expect(state.detections.get(d1.detection_id)?.confidence).toBe(75);
    state = apply(state, { type: 'detection', seq: 2, detection: makeDetection(9) });
    expect(state.detections.size).toBe(1);
  });

  it('moves the selection to merged_into when a detection is removed (TC-WS-005)', () => {
    const kept = makeDetection(1);
    const merged = makeDetection(2);
    let state = apply(
      INITIAL_STATE,
      { type: 'detection', seq: 1, detection: kept },
      { type: 'detection', seq: 2, detection: merged },
    );
    state = liveReducer(state, { type: 'select', id: merged.detection_id });
    state = apply(state, { type: 'detection_removed', seq: 3, detection_id: merged.detection_id, merged_into: kept.detection_id });
    expect(state.detections.has(merged.detection_id)).toBe(false);
    expect(state.selectedId).toBe(kept.detection_id);
  });

  it('tracks progress, track chunks, warnings and the terminal status', () => {
    const state = apply(
      INITIAL_STATE,
      { type: 'progress', seq: 1, stage: 'detect', percent: 46, eta_s: 22, pings_total: 18240 },
      { type: 'track', seq: 2, ping_start: 0, ping_end: 400, points: [[13, 80], [13.1, 80.1], [13.2, 80.2], [13.3, 80.3], [13.4, 80.4]] },
      { type: 'warning', seq: 3, code: 'DROPOUT', message: 'DROPOUT pings', ping_start: 100, ping_end: 200 },
      { type: 'done', seq: 4, status: 'completed_with_warnings', summary: { total_detections: 0, by_class: {}, by_tier: {} }, report_urls: { csv: '/x.csv' } },
    );
    expect(state.status).toBe('completed_with_warnings');
    expect(state.pingsTotal).toBe(18240);
    expect(state.reportUrls).toEqual({ csv: '/x.csv' });
    const segments = qualitySegmentsOf(state.chunks, state.warnings, []);
    expect(segments).toHaveLength(1);
    expect(segments[0]?.points).toEqual([[13.1, 80.1], [13.2, 80.2]]);
  });

  it('falls back to the nearest track point for a short ping range', () => {
    const chunks = [{ ping_start: 0, ping_end: 100, points: [[1, 1], [2, 2]] as [number, number][] }];
    expect(pointsForPings(chunks, 40, 45)).toEqual([[1, 1]]);
  });

  it('loads stored results with track quality segments', () => {
    const state = liveReducer(INITIAL_STATE, {
      type: 'loaded',
      detections: [makeDetection(1)],
      status: 'completed',
      track: {
        type: 'FeatureCollection',
        features: [
          { type: 'Feature', properties: { segment: 'track' }, geometry: { type: 'LineString', coordinates: [[80, 13], [80.1, 13.1]] } },
          {
            type: 'Feature',
            properties: { segment: 'quality', code: 'HIGH_MOTION', ping_start: 5, ping_end: 9 },
            geometry: { type: 'LineString', coordinates: [[80.05, 13.05], [80.06, 13.06]] },
          },
        ],
      },
    });
    expect(state.loadedTrack).toEqual([[13, 80], [13.1, 80.1]]);
    expect(state.warnings).toEqual([{ code: 'HIGH_MOTION', message: 'HIGH_MOTION pings 5–9', ping_start: 5, ping_end: 9 }]);
    expect(state.detections.size).toBe(1);
  });
});
