import { describe, expect, it } from 'vitest';

import { makeDetection, makeDetections } from '../test/fixtures';
import {
  DEFAULT_FILTERS,
  filterAndSort,
  filterDetections,
  filtersFromSearch,
  filtersToSearch,
  sortDetections,
  toDetectionQuery,
  type Filters,
} from './filters';

describe('detection filters (ST-093)', () => {
  it('filters and sorts 2,000 detections in under 100 ms (TC-UI-004)', () => {
    const detections = makeDetections(2000);
    const variants: Filters[] = [
      DEFAULT_FILTERS,
      { ...DEFAULT_FILTERS, minConf: 60, classes: ['ghost_net', 'pipe'] },
      { ...DEFAULT_FILTERS, tiers: ['hazard'], sort: 'ping' },
    ];
    for (const filters of variants) {
      const start = performance.now();
      const result = filterAndSort(detections, filters);
      expect(performance.now() - start).toBeLessThan(100);
      expect(result.every((d) => d.confidence >= filters.minConf)).toBe(true);
    }
  });

  it('matches the API semantics: inclusive bounds, membership, any-of flags', () => {
    const a = makeDetection(1, { confidence: 30, quality_flags: ['DROPOUT'] });
    const b = makeDetection(2, { confidence: 100, quality_flags: ['HIGH_MOTION', 'NEAR_NADIR'] });
    const c = makeDetection(3, { confidence: 29.9 });
    const rejected = makeDetection(4, {
      confidence: 70,
      review: { status: 'rejected', reviewer: 'a', reject_reason: 'rock', note: null, updated_utc: null },
    });
    const list = [a, b, c, rejected];
    expect(filterDetections(list, { ...DEFAULT_FILTERS, tiers: ['hazard', 'review', 'anomaly', 'hidden'] })).toEqual([a, b, rejected]);
    expect(filterDetections(list, { ...DEFAULT_FILTERS, flags: ['DROPOUT', 'NEAR_NADIR'] })).toEqual([a, b]);
    expect(filterDetections(list, { ...DEFAULT_FILTERS, reviewStatuses: ['rejected'] })).toEqual([rejected]);
    expect(filterDetections(list, { ...DEFAULT_FILTERS, classes: [] })).toEqual([]);
  });

  it('sorts by confidence, area, ping and class', () => {
    const list = [makeDetection(1, { confidence: 40 }), makeDetection(2, { confidence: 90 }), makeDetection(3, { confidence: 60 })];
    expect(sortDetections(list, '-confidence').map((d) => d.confidence)).toEqual([90, 60, 40]);
    expect(sortDetections(list, 'confidence').map((d) => d.confidence)).toEqual([40, 60, 90]);
    expect(sortDetections(list, '-area').map((d) => d.detection_id.slice(-1))).toEqual(['3', '2', '1']);
    expect(sortDetections(list, 'ping').map((d) => d.detection_id.slice(-1))).toEqual(['1', '2', '3']);
    expect(sortDetections(list, 'class').map((d) => d.class)).toEqual(['cylinder', 'pipe', 'shipwreck']);
  });

  it('round-trips through the URL and keeps other parameters', () => {
    expect(filtersToSearch(DEFAULT_FILTERS).toString()).toBe('');
    const custom: Filters = {
      classes: ['ghost_net'],
      minConf: 60,
      maxConf: 95,
      tiers: ['hazard', 'review'],
      flags: ['DROPOUT'],
      reviewStatuses: ['pending'],
      sort: 'ping',
    };
    const params = filtersToSearch(custom, new URLSearchParams('job=JOB-1'));
    expect(params.get('job')).toBe('JOB-1');
    expect(filtersFromSearch(params)).toEqual(custom);
    expect(filtersFromSearch(new URLSearchParams('min_conf=abc&tier=bogus,hazard&sort=nope'))).toMatchObject({
      minConf: 30,
      tiers: ['hazard'],
      sort: '-confidence',
    });
  });

  it('converts to API query parameters for the filtered report scope', () => {
    expect(toDetectionQuery(DEFAULT_FILTERS)).toEqual({
      class: undefined,
      tier: ['hazard', 'review', 'anomaly'],
      min_conf: 30,
      max_conf: 100,
      review_status: undefined,
      flags: undefined,
    });
  });
});
