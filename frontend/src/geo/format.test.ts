import { describe, expect, it } from 'vitest';

import { copyText, formatDd, toDms } from './format';

describe('coordinate formatting (same strings as geo/formatting.py, TC-GEO-014)', () => {
  it('matches the Python to_dms outputs', () => {
    expect(toDms(13.08412, 'lat')).toBe('13° 05\' 02.83" N');
    expect(toDms(80.31275, 'lon')).toBe('80° 18\' 45.90" E');
    expect(toDms(-33.9, 'lat')).toBe('33° 54\' 00.00" S');
    expect(toDms(10.999999, 'lon')).toBe('11° 00\' 00.00" E');
  });

  it('rejects out-of-range values', () => {
    expect(() => toDms(91, 'lat')).toThrow(RangeError);
    expect(() => toDms(-180.5, 'lon')).toThrow(RangeError);
  });

  it('formats decimal degrees and the copy text with 6 decimals', () => {
    expect(formatDd(13.08412)).toBe('13.084120');
    expect(copyText(13.08412, 80.31275)).toBe('13.084120, 80.312750');
  });
});
