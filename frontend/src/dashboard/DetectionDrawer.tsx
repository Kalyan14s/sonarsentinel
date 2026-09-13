import { useState, type RefObject } from 'react';

import {
  api,
  ApiError,
  REJECT_REASONS,
  type ChipOverlay,
  type Detection,
  type RejectReason,
  type ReviewRequest,
} from '../api/client';
import { copyText, formatDd, toDms } from '../geo/format';
import { CLASS_STYLES, TIER_LABELS, type AlertTier, type DetectionClass } from '../tokens';
import { ALL_CLASSES } from './filters';
import { FLAG_HELP, REVIEW_LABELS, shortId } from './labels';
import styles from './DetectionDrawer.module.css';

const OVERLAYS: { value: ChipOverlay; label: string }[] = [
  { value: 'mask', label: 'Mask' },
  { value: 'shadow', label: 'Shadow' },
  { value: 'anomaly', label: 'Anomaly' },
  { value: 'none', label: 'Off' },
];
const OVERLAY_KEY = 'ss-chip-overlay';

function storedOverlay(): ChipOverlay {
  try {
    const value = sessionStorage.getItem(OVERLAY_KEY);
    return OVERLAYS.some((o) => o.value === value) ? (value as ChipOverlay) : 'mask';
  } catch {
    return 'mask';
  }
}

function rememberOverlay(value: ChipOverlay): void {
  try {
    sessionStorage.setItem(OVERLAY_KEY, value);
  } catch {
    // session storage unavailable: the choice lasts until the drawer closes
  }
}

const value = (v: number | null | undefined, unit = '') => (v === null || v === undefined ? '—' : `${v}${unit}`);

interface DetectionDrawerProps {
  detection: Detection;
  index: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
  onClose: () => void;
  onReviewed: (detection: Detection) => void;
  onZoom?: (detection: Detection) => void;
  drawerRef?: RefObject<HTMLElement>;
}

/** S-03 detection detail (ST-094): evidence, exact location, size, score breakdown, review. */
export function DetectionDrawer({
  detection: d,
  index,
  total,
  onPrev,
  onNext,
  onClose,
  onReviewed,
  onZoom,
  drawerRef,
}: DetectionDrawerProps) {
  const [overlay, setOverlay] = useState<ChipOverlay>(storedOverlay);
  const [attempt, setAttempt] = useState(0);
  const [chipFailed, setChipFailed] = useState(false);
  const [chipLoaded, setChipLoaded] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [mode, setMode] = useState<'idle' | 'reject' | 'reclassify'>('idle');
  const [reason, setReason] = useState<RejectReason | ''>('');
  const [newClass, setNewClass] = useState<string>('');
  const [note, setNote] = useState(d.review.note ?? '');
  const [busy, setBusy] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);

  const cls = d.class as DetectionClass;
  const tier = d.alert_tier as AlertTier;
  const { lat, lon } = d.position;
  const geotagged = lat !== null && lon !== null;
  const scores = d.scores;
  const penalties = [
    scores.dropout_penalty ? `dropout −${scores.dropout_penalty.toFixed(2)}` : null,
    scores.motion_penalty ? `motion −${scores.motion_penalty.toFixed(2)}` : null,
  ].filter(Boolean);
  const lowQuality = d.quality_flags.includes('DROPOUT') || d.quality_flags.includes('HIGH_MOTION');

  const copy = async (text: string, message: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setToast(message);
    } catch {
      setToast('Copy failed — select the text manually');
    }
  };

  const submit = async (body: ReviewRequest) => {
    setBusy(true);
    setReviewError(null);
    try {
      const updated = await api.reviewDetection(d.detection_id, { ...body, note: note || undefined });
      setMode('idle');
      onReviewed(updated);
    } catch (err) {
      setReviewError(err instanceof ApiError || err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const chipSrc = `${api.chipUrl(d.detection_id, overlay)}${attempt ? `&retry=${attempt}` : ''}`;
  const bars: { label: string; score: number | undefined; note?: string }[] = [
    { label: 'Detector', score: scores.detector },
    { label: 'Anomaly', score: scores.anomaly },
    { label: 'Shadow check', score: scores.shadow },
    { label: 'False-positive filter', score: scores.fp_filter },
    { label: 'Seen in other lines', score: scores.persistence, note: `(${d.n_views} view${d.n_views === 1 ? '' : 's'})` },
  ];

  return (
    <section ref={drawerRef} className={styles.drawer} aria-label="Detection detail">
      <div className={styles.nav}>
        <button type="button" onClick={onClose}>
          ← Back to list
        </button>
        <span>
          {shortId(d.detection_id)} · {index + 1} of {total}
        </span>
        <button type="button" onClick={onPrev} disabled={index <= 0} aria-label="Previous detection">
          ‹
        </button>
        <button type="button" onClick={onNext} disabled={index >= total - 1} aria-label="Next detection">
          ›
        </button>
        <button type="button" onClick={onClose} aria-label="Close detail">
          ×
        </button>
      </div>

      <header className={styles.header}>
        <h2 className={styles.title}>
          <span className={styles.swatch} style={{ background: CLASS_STYLES[cls].color }} aria-hidden />
          {CLASS_STYLES[cls].label}
          <span className={styles.conf}>{d.confidence.toFixed(1)}%</span>
          <span className={`${styles.badge} ${styles[`tier_${tier}`]}`}>{TIER_LABELS[tier]}</span>
        </h2>
        <button
          type="button"
          className={styles.idButton}
          title="Copy detection ID"
          onClick={() => void copy(d.detection_id, `Copied ${d.detection_id}`)}
        >
          {d.detection_id}
        </button>
      </header>

      <div className={styles.chip}>
        {chipFailed ? (
          <div className={styles.placeholder}>
            <p>Preview not generated</p>
            <button
              type="button"
              onClick={() => {
                setChipFailed(false);
                setChipLoaded(false);
                setAttempt((n) => n + 1);
              }}
            >
              Retry
            </button>
          </div>
        ) : (
          <img
            key={chipSrc}
            src={chipSrc}
            width={256}
            height={256}
            className={chipLoaded ? styles.chipImage : `${styles.chipImage} ${styles.skeleton}`}
            alt={`Sonar chip of ${shortId(d.detection_id)} with ${overlay === 'none' ? 'no' : overlay} overlay`}
            onLoad={() => setChipLoaded(true)}
            onError={() => setChipFailed(true)}
          />
        )}
        <fieldset className={styles.overlays}>
          <legend>Overlay</legend>
          {OVERLAYS.map((o) => (
            <label key={o.value}>
              <input
                type="radio"
                name="chip-overlay"
                value={o.value}
                checked={overlay === o.value}
                onChange={() => {
                  setOverlay(o.value);
                  rememberOverlay(o.value);
                  setChipFailed(false);
                  setChipLoaded(false);
                }}
              />
              {o.label}
            </label>
          ))}
        </fieldset>
        {geotagged && onZoom && (
          <button type="button" onClick={() => onZoom(d)}>
            Zoom map to object
          </button>
        )}
      </div>

      <section className={styles.section} aria-label="Location">
        <h3>Location (WGS84)</h3>
        {geotagged ? (
          <>
            <dl className={styles.grid}>
              <dt>Lat</dt>
              <dd className={styles.mono}>{formatDd(lat)}</dd>
              <dd className={styles.mono}>{toDms(lat, 'lat')}</dd>
              <dt>Lon</dt>
              <dd className={styles.mono}>{formatDd(lon)}</dd>
              <dd className={styles.mono}>{toDms(lon, 'lon')}</dd>
            </dl>
            <button type="button" onClick={() => void copy(copyText(lat, lon), `Copied ${copyText(lat, lon)}`)}>
              Copy coordinates
            </button>
          </>
        ) : (
          <div className={styles.warning}>
            <p>[!] No GPS for this image</p>
            {d.sonar_ref.pixel_bbox && (
              <p className={styles.mono}>
                Pixel box x {d.sonar_ref.pixel_bbox[0]}–{d.sonar_ref.pixel_bbox[2]}, y {d.sonar_ref.pixel_bbox[1]}–
                {d.sonar_ref.pixel_bbox[3]}
              </p>
            )}
          </div>
        )}
        <dl className={styles.pairs}>
          <dt>Depth</dt>
          <dd>{value(d.position.depth_m, ' m')}</dd>
          <dt>Uncertainty</dt>
          <dd>{d.position.uncertainty_m === null ? '—' : `± ${d.position.uncertainty_m} m`}</dd>
        </dl>
      </section>

      <section className={styles.section} aria-label="Size">
        <h3>Size</h3>
        <dl className={styles.pairs}>
          <dt>Length × width</dt>
          <dd>
            {d.dimensions.length_m === null || d.dimensions.width_m === null
              ? '—'
              : `${d.dimensions.length_m} m × ${d.dimensions.width_m} m`}
          </dd>
          <dt>Area</dt>
          <dd>{value(d.dimensions.area_m2, ' m²')}</dd>
          <dt>Height</dt>
          <dd>{d.dimensions.height_m === null ? 'n/a' : `~${d.dimensions.height_m} m`}</dd>
          <dt>Orientation</dt>
          <dd>{d.orientation_deg === null ? '—' : `${d.orientation_deg}° from N`}</dd>
        </dl>
      </section>

      <section className={styles.section} aria-label="Why this confidence">
        <h3>Why {Math.round(d.confidence)}%?</h3>
        <ul className={styles.bars}>
          {bars.map((bar) => (
            <li key={bar.label}>
              <span>{bar.label}</span>
              {bar.score === undefined ? (
                <span className={styles.muted}>not used</span>
              ) : (
                <>
                  <span className={styles.track} aria-hidden>
                    <span className={styles.fill} style={{ width: `${Math.round(bar.score * 100)}%` }} />
                  </span>
                  <span className={styles.mono}>
                    {bar.score.toFixed(2)} {bar.note}
                  </span>
                </>
              )}
            </li>
          ))}
        </ul>
        <p>Quality penalties: {penalties.length ? penalties.join(', ') : 'none'}</p>
        <p>
          Fused {scores.fused.toFixed(2)} → calibrated {d.confidence.toFixed(1)}%
        </p>
      </section>

      <section className={styles.section} aria-label="Sonar reference">
        <h3>Sonar reference</h3>
        <p>
          {d.sonar_ref.source_file} · {d.sonar_ref.side}
          {d.sonar_ref.ping_start !== undefined && d.sonar_ref.ping_start !== null
            ? ` · pings ${d.sonar_ref.ping_start}–${d.sonar_ref.ping_end}`
            : ''}
        </p>
        <p>
          Ground range {value(d.sonar_ref.ground_range_m, ' m')} · {d.sonar_ref.time_utc ?? 'time n/a'}
        </p>
        <div className={styles.flags}>
          Quality flags:{' '}
          {d.quality_flags.length
            ? d.quality_flags.map((flag) => (
                <span key={flag} className={styles.flag} title={FLAG_HELP[flag]}>
                  [!] {flag}
                </span>
              ))
            : 'none'}
        </div>
        {lowQuality && <p className={styles.warning}>Data quality is poor here. Consider re-surveying this area.</p>}
      </section>

      <section className={styles.section} aria-label="Review">
        <h3>Review</h3>
        <p>
          Status: {REVIEW_LABELS[d.review.status]}
          {d.review.reviewer ? ` by ${d.review.reviewer}` : ''}
          {d.review.reject_reason ? ` (${d.review.reject_reason})` : ''}
        </p>
        <div className={styles.actions}>
          <button type="button" disabled={busy} onClick={() => void submit({ review_status: 'confirmed' })}>
            Confirm
          </button>
          <button type="button" disabled={busy} onClick={() => setMode('reject')}>
            Reject
          </button>
          <button type="button" disabled={busy} onClick={() => setMode('reclassify')}>
            Reclassify
          </button>
        </div>
        {mode === 'reject' && (
          <div className={styles.form}>
            <label>
              Reason (required)
              <select value={reason} onChange={(e) => setReason(e.target.value as RejectReason | '')}>
                <option value="">Choose a reason…</option>
                {REJECT_REASONS.map((r) => (
                  <option key={r} value={r}>
                    {r.charAt(0).toUpperCase() + r.slice(1)}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              disabled={busy || !reason}
              onClick={() => reason && void submit({ review_status: 'rejected', reject_reason: reason })}
            >
              Submit rejection
            </button>
          </div>
        )}
        {mode === 'reclassify' && (
          <div className={styles.form}>
            <label>
              New class
              <select value={newClass} onChange={(e) => setNewClass(e.target.value)}>
                <option value="">Choose a class…</option>
                {ALL_CLASSES.filter((c) => c !== d.class).map((c) => (
                  <option key={c} value={c}>
                    {CLASS_STYLES[c].label}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              disabled={busy || !newClass}
              onClick={() => newClass && void submit({ review_status: 'reclassified', class: newClass })}
            >
              Submit class
            </button>
          </div>
        )}
        <label className={styles.note}>
          Note
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} />
        </label>
        {reviewError && (
          <p role="alert" className={styles.error}>
            Review failed: {reviewError}
          </p>
        )}
      </section>

      {toast && (
        <p role="status" className={styles.toast}>
          {toast}
        </p>
      )}
    </section>
  );
}
