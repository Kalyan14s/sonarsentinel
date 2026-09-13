import type { RefObject } from 'react';

import type { QualityFlag, ReviewStatus } from '../api/client';
import { CLASS_STYLES, TIER_LABELS, type AlertTier, type DetectionClass } from '../tokens';
import {
  ALL_CLASSES,
  ALL_REVIEW_STATUSES,
  ALL_TIERS,
  DEFAULT_FILTERS,
  FILTERABLE_FLAGS,
  type Counts,
  type Filters,
} from './filters';
import { FLAG_HELP, REVIEW_LABELS } from './labels';
import styles from './FilterPanel.module.css';

interface FilterPanelProps {
  filters: Filters;
  counts: Counts;
  onChange: (filters: Filters) => void;
  panelRef?: RefObject<HTMLElement>;
}

function toggle<T>(list: readonly T[], value: T): T[] {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
}

/** S-02 filters panel (ST-093): changes apply instantly to map, list and filtered export. */
export function FilterPanel({ filters, counts, onChange, panelRef }: FilterPanelProps) {
  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch });

  return (
    <section ref={panelRef} aria-label="Filters" className={styles.panel}>
      <h2 className={styles.heading}>Filters</h2>

      <fieldset className={styles.fieldset}>
        <legend>Class</legend>
        {ALL_CLASSES.map((cls: DetectionClass) => (
          <label key={cls} className={styles.option}>
            <input
              type="checkbox"
              checked={filters.classes.includes(cls)}
              onChange={() => set({ classes: toggle(filters.classes, cls) })}
            />
            <span className={styles.swatch} style={{ background: CLASS_STYLES[cls].color }} aria-hidden />
            <span>{CLASS_STYLES[cls].label}</span>
            <span className={styles.count}>{counts.classes[cls] ?? 0}</span>
          </label>
        ))}
      </fieldset>

      <fieldset className={styles.fieldset}>
        <legend>
          Confidence {filters.minConf}–{filters.maxConf}%
        </legend>
        <label className={styles.range}>
          <span>Minimum</span>
          <input
            type="range"
            min={0}
            max={100}
            step={1}
            value={filters.minConf}
            aria-label="Minimum confidence"
            onChange={(e) => {
              const minConf = Number(e.target.value);
              set({ minConf, maxConf: Math.max(minConf, filters.maxConf) });
            }}
          />
        </label>
        <label className={styles.range}>
          <span>Maximum</span>
          <input
            type="range"
            min={0}
            max={100}
            step={1}
            value={filters.maxConf}
            aria-label="Maximum confidence"
            onChange={(e) => {
              const maxConf = Number(e.target.value);
              set({ maxConf, minConf: Math.min(maxConf, filters.minConf) });
            }}
          />
        </label>
      </fieldset>

      <fieldset className={styles.fieldset}>
        <legend>Alert tier</legend>
        {ALL_TIERS.map((tier: AlertTier) => (
          <label key={tier} className={styles.option}>
            <input
              type="checkbox"
              checked={filters.tiers.includes(tier)}
              onChange={() => set({ tiers: toggle(filters.tiers, tier) })}
            />
            <span>{tier === 'hidden' ? 'Hidden (low)' : TIER_LABELS[tier][0] + TIER_LABELS[tier].slice(1).toLowerCase()}</span>
            <span className={styles.count}>{counts.tiers[tier] ?? 0}</span>
          </label>
        ))}
      </fieldset>

      <fieldset className={styles.fieldset}>
        <legend>Quality flags (any)</legend>
        {FILTERABLE_FLAGS.map((flag: QualityFlag) => (
          <label key={flag} className={styles.option} title={FLAG_HELP[flag]}>
            <input
              type="checkbox"
              checked={filters.flags.includes(flag)}
              onChange={() => set({ flags: toggle(filters.flags, flag) })}
            />
            <span className={styles.flag}>{flag}</span>
          </label>
        ))}
      </fieldset>

      <fieldset className={styles.fieldset}>
        <legend>Review status</legend>
        {ALL_REVIEW_STATUSES.map((status: ReviewStatus) => (
          <label key={status} className={styles.option}>
            <input
              type="checkbox"
              checked={filters.reviewStatuses.includes(status)}
              onChange={() => set({ reviewStatuses: toggle(filters.reviewStatuses, status) })}
            />
            <span>{REVIEW_LABELS[status]}</span>
          </label>
        ))}
      </fieldset>

      <button type="button" className={styles.reset} onClick={() => onChange({ ...DEFAULT_FILTERS, sort: filters.sort })}>
        Reset filters
      </button>
    </section>
  );
}
