import { useEffect, useLayoutEffect, useState, type ReactNode, type RefObject } from 'react';

import type { Detection, DetectionSort } from '../api/client';
import { CLASS_STYLES, TIER_LABELS, type AlertTier, type DetectionClass } from '../tokens';
import { locationText, shortId, sizeText, SORT_OPTIONS } from './labels';
import styles from './DetectionList.module.css';

const ROW_PX = 72;
const OVERSCAN = 8;
const FALLBACK_ROWS = 30;

interface DetectionListProps {
  detections: readonly Detection[];
  selectedId: string | null;
  sort: DetectionSort;
  onSortChange: (sort: DetectionSort) => void;
  onSelect: (id: string) => void;
  listRef?: RefObject<HTMLDivElement>;
  empty?: ReactNode;
}

/**
 * S-02 detection list (ST-093). Rows are windowed (fixed 72 px height) so 2,000 detections scroll
 * and filter without rendering every card.
 */
export function DetectionList({ detections, selectedId, sort, onSortChange, onSelect, listRef, empty }: DetectionListProps) {
  const [scrollTop, setScrollTop] = useState(0);
  const [viewport, setViewport] = useState(0);

  useLayoutEffect(() => {
    setViewport(listRef?.current?.clientHeight ?? 0);
  }, [listRef]);

  useEffect(() => {
    const element = listRef?.current;
    const index = detections.findIndex((d) => d.detection_id === selectedId);
    if (!element || index < 0) return;
    const top = index * ROW_PX;
    if (top < element.scrollTop) element.scrollTop = top;
    else if (element.clientHeight && top + ROW_PX > element.scrollTop + element.clientHeight) {
      element.scrollTop = top + ROW_PX - element.clientHeight;
    }
  }, [selectedId, detections, listRef]);

  const height = viewport || ROW_PX * FALLBACK_ROWS;
  const start = Math.max(0, Math.floor(scrollTop / ROW_PX) - OVERSCAN);
  const end = Math.min(detections.length, Math.ceil((scrollTop + height) / ROW_PX) + OVERSCAN);

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <h2 className={styles.heading}>Detections ({detections.length})</h2>
        <label className={styles.sort}>
          Sort
          <select value={sort} onChange={(e) => onSortChange(e.target.value as DetectionSort)}>
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {detections.length === 0 ? (
        <div className={styles.empty}>{empty}</div>
      ) : (
        <div
          ref={listRef}
          className={styles.list}
          role="listbox"
          aria-label="Detections"
          tabIndex={0}
          aria-activedescendant={selectedId ? `det-${selectedId}` : undefined}
          onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
        >
          <div style={{ height: detections.length * ROW_PX, position: 'relative' }}>
            {detections.slice(start, end).map((d, offset) => {
              const cls = d.class as DetectionClass;
              const selected = d.detection_id === selectedId;
              return (
                <div
                  key={d.detection_id}
                  id={`det-${d.detection_id}`}
                  role="option"
                  aria-selected={selected}
                  className={selected ? `${styles.row} ${styles.selected}` : styles.row}
                  style={{ top: (start + offset) * ROW_PX, height: ROW_PX }}
                  onClick={() => onSelect(d.detection_id)}
                >
                  <span className={styles.swatch} style={{ background: CLASS_STYLES[cls].color }} aria-hidden />
                  <span className={styles.title}>
                    {CLASS_STYLES[cls].label} <span className={styles.id}>{shortId(d.detection_id)}</span>
                  </span>
                  <span className={styles.conf}>{d.confidence.toFixed(1)}%</span>
                  <span className={`${styles.badge} ${styles[`tier_${d.alert_tier}`]}`}>
                    {TIER_LABELS[d.alert_tier as AlertTier]}
                  </span>
                  <span className={styles.meta}>{sizeText(d)}</span>
                  <span className={`${styles.meta} ${styles.mono}`}>{locationText(d)}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
