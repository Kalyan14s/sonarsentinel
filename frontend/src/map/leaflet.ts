/**
 * Leaflet with the global `L` that the UMD build of leaflet.markercluster expects.
 * Import this module before `leaflet.markercluster` so the global exists when the plugin loads.
 */
import L from 'leaflet';

(globalThis as unknown as { L: typeof L }).L = L;

export default L;
