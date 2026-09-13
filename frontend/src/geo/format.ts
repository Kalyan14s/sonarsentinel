/**
 * Coordinate formatting identical to backend/sonarsentinel/geo/formatting.py (TC-GEO-014), so the
 * dashboard shows exactly what the CSV/JSON exports contain (S-03 acceptance, TC-UI-005).
 */

export type Axis = 'lat' | 'lon';

/** Decimal degrees with a fixed number of decimals (6 ≈ 0.11 m), like Python `f"{v:.6f}"`. */
export function formatDd(value: number, decimals = 6): string {
  return value.toFixed(decimals);
}

/** Python's `round()`: round half to even. */
function roundHalfEven(value: number): number {
  const floor = Math.floor(value);
  const diff = value - floor;
  if (diff > 0.5) return floor + 1;
  if (diff < 0.5) return floor;
  return floor % 2 === 0 ? floor : floor + 1;
}

/** `DD° MM' SS.SS" H`, e.g. `13° 05' 02.83" N`; integer hundredths avoid 59.999… rounding. */
export function toDms(value: number, axis: Axis): string {
  const limit = axis === 'lat' ? 90 : 180;
  if (!(value >= -limit && value <= limit)) throw new RangeError(`${axis} out of range: ${value}`);
  const hemisphere = axis === 'lat' ? (value >= 0 ? 'N' : 'S') : value >= 0 ? 'E' : 'W';
  const totalHundredths = roundHalfEven(Math.abs(value) * 3600 * 100);
  const degrees = Math.floor(totalHundredths / 360_000);
  const rest = totalHundredths % 360_000;
  const minutes = Math.floor(rest / 6000);
  const seconds = (rest % 6000) / 100;
  return `${degrees}° ${String(minutes).padStart(2, '0')}' ${seconds.toFixed(2).padStart(5, '0')}" ${hemisphere}`;
}

/** Text copied by the coordinate copy button: `"13.084120, 80.312750"`. */
export function copyText(lat: number, lon: number): string {
  return `${formatDd(lat)}, ${formatDd(lon)}`;
}
