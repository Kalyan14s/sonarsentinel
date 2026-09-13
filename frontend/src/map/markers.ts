import { CLASS_STYLES, type AlertTier, type DetectionClass } from '../tokens';

/** Class shape + tier style as the HTML of a Leaflet divIcon (docs/wireframes/README.md §4). */
export function markerHtml(cls: DetectionClass, tier: AlertTier): string {
  const style = CLASS_STYLES[cls];
  return `<span class="ss-marker ss-${style.shape} ss-tier-${tier}" style="--marker:${style.color}"></span>`;
}
