import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import {
  api,
  REJECT_REASONS,
  type ChipOverlay,
  type Detection,
  type ReviewRequest,
  type SurveySummary,
} from '../api/client';
import { ALL_CLASSES } from '../dashboard/filters';
import { REVIEW_LABELS, shortId, sizeText } from '../dashboard/labels';
import { formatDd, toDms } from '../geo/format';
import { MapView } from '../map/MapView';
import {
  applyDecision,
  DEFAULT_TIERS,
  isPending,
  keyAction,
  movePending,
  nextPendingId,
  REVIEW_TIERS,
  summarizeDecisions,
  UNDO_WINDOW_MS,
  whyText,
  type DecisionMode,
  type KeyAction,
  type ReviewTier,
} from '../review/reviewModel';
import { CLASS_STYLES, TIER_LABELS, type AlertTier, type DetectionClass } from '../tokens';
import styles from './ReviewPage.module.css';

type SaveState = 'saving' | 'retrying' | 'failed';

const TIER_NAMES: Record<ReviewTier, string> = { review: 'Review', anomaly: 'Anomaly', hazard: 'Hazard' };
const OVERLAYS: { value: ChipOverlay; label: string }[] = [
  { value: 'mask', label: 'Mask' },
  { value: 'shadow', label: 'Shadow' },
  { value: 'anomaly', label: 'Anomaly' },
  { value: 'none', label: 'Off' },
];
const capitalise = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

function isTextField(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.tagName === 'TEXTAREA' || target.isContentEditable) return true;
  return target instanceof HTMLInputElement && ['text', 'search', 'number'].includes(target.type);
}

/** S-05 Review queue (ST-096): keyboard-first confirm / reject / reclassify with optimistic saves. */
export function ReviewPage() {
  const params = useParams();
  const navigate = useNavigate();
  const [surveys, setSurveys] = useState<SurveySummary[] | null>(null);
  const [surveyId, setSurveyId] = useState<string | null>(params.surveyId ?? null);
  const [tiers, setTiers] = useState<ReviewTier[]>(DEFAULT_TIERS);
  const [items, setItems] = useState<Detection[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [mode, setMode] = useState<DecisionMode>('idle');
  const [note, setNote] = useState('');
  const [overlay, setOverlay] = useState<ChipOverlay>('mask');
  const [autoAdvance, setAutoAdvance] = useState(true);
  const [saves, setSaves] = useState<Record<string, SaveState>>({});
  const undoRef = useRef<{ id: string; previous: Detection; at: number } | null>(null);
  const failedBodies = useRef<Record<string, ReviewRequest>>({});

  useEffect(() => {
    let active = true;
    api
      .surveys({ limit: 50 })
      .then((page) => {
        if (!active) return;
        setSurveys(page.items);
        setSurveyId((id) => id ?? page.items[0]?.survey_id ?? null);
      })
      .catch((err: unknown) => active && setLoadError(err instanceof Error ? err.message : String(err)));
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!surveyId) return;
    let active = true;
    setItems(null);
    setLoadError(null);
    api
      .detections(surveyId, { tier: tiers, sort: 'confidence', limit: 5000 })
      .then((page) => {
        if (!active) return;
        setItems(page.items);
        setCurrentId(page.items.find(isPending)?.detection_id ?? null);
        setMode('idle');
      })
      .catch((err: unknown) => active && setLoadError(err instanceof Error ? err.message : String(err)));
    return () => {
      active = false;
    };
  }, [surveyId, tiers]);

  const survey = surveys?.find((s) => s.survey_id === surveyId) ?? null;
  const pending = useMemo(() => (items ?? []).filter(isPending), [items]);
  const done = useMemo(() => (items ?? []).filter((d) => !isPending(d)), [items]);
  const current = items?.find((d) => d.detection_id === currentId) ?? null;
  const currentList = useMemo(() => (current ? [current] : []), [current]);

  const setSave = (id: string, state: SaveState | null) =>
    setSaves((prev) => {
      const next = { ...prev };
      if (state) next[id] = state;
      else delete next[id];
      return next;
    });

  const persist = async (id: string, body: ReviewRequest) => {
    setSave(id, 'saving');
    for (const attempt of [1, 2]) {
      try {
        const updated = await api.reviewDetection(id, body);
        setItems((list) => list?.map((d) => (d.detection_id === id ? updated : d)) ?? list);
        delete failedBodies.current[id];
        setSave(id, null);
        return;
      } catch {
        if (attempt === 1) setSave(id, 'retrying');
      }
    }
    failedBodies.current[id] = body;
    setSave(id, 'failed');
  };

  const decide = (partial: ReviewRequest) => {
    if (!current || !items) return;
    const body: ReviewRequest = note.trim() ? { ...partial, note: note.trim() } : partial;
    undoRef.current = { id: current.detection_id, previous: current, at: Date.now() };
    const updated = items.map((d) => (d.detection_id === current.detection_id ? applyDecision(d, body) : d));
    setItems(updated);
    setMode('idle');
    setNote('');
    if (autoAdvance) setCurrentId(nextPendingId(updated, current.detection_id));
    void persist(current.detection_id, body);
  };

  const undo = () => {
    const last = undoRef.current;
    if (!last || !items || Date.now() - last.at > UNDO_WINDOW_MS) return;
    undoRef.current = null;
    setItems(items.map((d) => (d.detection_id === last.id ? last.previous : d)));
    setCurrentId(last.id);
    setMode('idle');
    void persist(last.id, { review_status: 'pending' });
  };

  const run = (action: KeyAction) => {
    switch (action.type) {
      case 'confirm':
        decide({ review_status: 'confirmed' });
        break;
      case 'reject-mode':
        if (current) setMode('reject');
        break;
      case 'reclassify-mode':
        if (current) setMode('reclassify');
        break;
      case 'reason':
        decide({ review_status: 'rejected', reject_reason: action.reason });
        break;
      case 'class':
        decide({ review_status: 'reclassified', class: action.cls });
        break;
      case 'skip':
      case 'next':
        setCurrentId(items ? movePending(items, currentId, 1) : currentId);
        setMode('idle');
        break;
      case 'prev':
        setCurrentId(items ? movePending(items, currentId, -1) : currentId);
        setMode('idle');
        break;
      case 'undo':
        undo();
        break;
      case 'cancel':
        setMode('idle');
        break;
    }
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      if (isTextField(event.target) && event.key !== 'Escape') return;
      const action = keyAction(event.key, mode, current?.class);
      if (!action) return;
      event.preventDefault();
      run(action);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  const toggleTier = (tier: ReviewTier) =>
    setTiers((prev) => (prev.includes(tier) ? prev.filter((t) => t !== tier) : [...prev, tier]));

  const mapLink = surveyId ? `/map/${encodeURIComponent(surveyId)}` : '/map';
  const total = items?.length ?? 0;
  const summary = summarizeDecisions(done);

  let body: React.ReactNode;
  if (loadError) {
    body = (
      <p role="alert" className={styles.error}>
        Could not load the review queue: {loadError}
      </p>
    );
  } else if (surveys !== null && surveys.length === 0) {
    body = (
      <p className={styles.empty}>
        No surveys yet. <Link to="/upload">Upload a sonar file</Link> to start.
      </p>
    );
  } else if (items === null) {
    body = <p role="status">Loading review queue…</p>;
  } else if (total === 0) {
    body = (
      <div className={styles.empty}>
        <p>Nothing to review — all detections are high-confidence or already reviewed.</p>
        <Link to={mapLink}>Back to map</Link>
      </div>
    );
  } else if (pending.length === 0 && !current) {
    body = (
      <div className={styles.complete} role="status">
        <h2>[ok] Review complete</h2>
        <p>
          {summary.reviewed} reviewed: {summary.confirmed} confirmed, {summary.rejected} rejected,{' '}
          {summary.reclassified} reclassified
        </p>
        {surveyId && <a href={api.reportUrl(surveyId, 'csv')}>Download updated report</a>}{' '}
        <Link to={mapLink}>Back to map</Link>
      </div>
    );
  } else {
    body = (
      <div className={styles.layout}>
        <aside className={styles.lists}>
          <h2>Pending ({pending.length})</h2>
          <ul className={styles.list} aria-label="Pending detections">
            {pending.map((d) => (
              <li key={d.detection_id}>
                <button
                  type="button"
                  aria-current={d.detection_id === currentId}
                  className={d.detection_id === currentId ? `${styles.item} ${styles.current}` : styles.item}
                  onClick={() => setCurrentId(d.detection_id)}
                >
                  <span className={styles.swatch} style={{ background: CLASS_STYLES[d.class as DetectionClass].color }} />
                  {CLASS_STYLES[d.class as DetectionClass].label} {shortId(d.detection_id)} · {d.confidence.toFixed(0)}% ·{' '}
                  {TIER_LABELS[d.alert_tier as AlertTier]}
                  <small>
                    {sizeText(d)} · {d.sonar_ref.side}
                  </small>
                </button>
              </li>
            ))}
          </ul>
          <h2>Done ({done.length})</h2>
          <ul className={styles.list} aria-label="Reviewed detections">
            {done.map((d) => (
              <li key={d.detection_id}>
                <button type="button" className={styles.item} onClick={() => setCurrentId(d.detection_id)}>
                  {shortId(d.detection_id)} {REVIEW_LABELS[d.review.status].toLowerCase()}
                  {d.review.reject_reason ? ` — ${d.review.reject_reason}` : ''}
                  {saves[d.detection_id] === 'failed' && <strong className={styles.error}> Not saved</strong>}
                </button>
                {saves[d.detection_id] === 'failed' && failedBodies.current[d.detection_id] && (
                  <button
                    type="button"
                    onClick={() => {
                      const retryBody = failedBodies.current[d.detection_id];
                      if (retryBody) void persist(d.detection_id, retryBody);
                    }}
                  >
                    Retry
                  </button>
                )}
              </li>
            ))}
          </ul>
        </aside>

        {current ? (
          <section className={styles.evidence} aria-label="Evidence">
            <h2>
              {shortId(current.detection_id)} · {CLASS_STYLES[current.class as DetectionClass].label} ·{' '}
              {current.confidence.toFixed(1)}% · {TIER_LABELS[current.alert_tier as AlertTier]}
              {!isPending(current) && ` · ${REVIEW_LABELS[current.review.status]}`}
            </h2>
            <div className={styles.media}>
              <div>
                <img
                  src={api.chipUrl(current.detection_id, overlay)}
                  width={256}
                  height={256}
                  className={styles.chip}
                  alt={`Sonar chip of ${shortId(current.detection_id)}`}
                />
                <fieldset className={styles.overlays}>
                  <legend>Overlay</legend>
                  {OVERLAYS.map((o) => (
                    <label key={o.value}>
                      <input
                        type="radio"
                        name="review-overlay"
                        checked={overlay === o.value}
                        onChange={() => setOverlay(o.value)}
                      />
                      {o.label}
                    </label>
                  ))}
                </fieldset>
              </div>
              <div className={styles.miniMap}>
                <MapView track={[]} quality={[]} detections={currentList} selected={current} />
              </div>
            </div>
            {current.position.lat !== null && current.position.lon !== null ? (
              <p className={styles.mono}>
                {formatDd(current.position.lat)}, {formatDd(current.position.lon)} ·{' '}
                {toDms(current.position.lat, 'lat')} {toDms(current.position.lon, 'lon')}
              </p>
            ) : (
              <p>No GPS — pixel coordinates only</p>
            )}
            <p>
              Depth {current.position.depth_m ?? '—'} m · ±{' '}
              {current.position.uncertainty_m === null ? '—' : `${current.position.uncertainty_m} m`} ·{' '}
              {sizeText(current)}
            </p>
            <p>{whyText(current)}</p>
            {saves[current.detection_id] === 'retrying' && <p role="status">Not saved — retrying</p>}

            <section className={styles.decision} aria-label="Decision">
              <h3>Is this a real man-made object?</h3>
              <div className={styles.buttons}>
                <button type="button" onClick={() => run({ type: 'confirm' })}>
                  Confirm (C)
                </button>
                <button type="button" aria-pressed={mode === 'reject'} onClick={() => run({ type: 'reject-mode' })}>
                  Reject (R)
                </button>
                <button
                  type="button"
                  aria-pressed={mode === 'reclassify'}
                  onClick={() => run({ type: 'reclassify-mode' })}
                >
                  Reclassify (K)
                </button>
              </div>
              {mode === 'reject' && (
                <div role="group" aria-label="Reject reason" className={styles.buttons}>
                  {REJECT_REASONS.map((reason, i) => (
                    <button key={reason} type="button" onClick={() => run({ type: 'reason', reason })}>
                      {i + 1} {capitalise(reason)}
                    </button>
                  ))}
                </div>
              )}
              {mode === 'reclassify' && (
                <div role="group" aria-label="New class" className={styles.buttons}>
                  {ALL_CLASSES.map((cls, i) => (
                    <button
                      key={cls}
                      type="button"
                      disabled={cls === current.class}
                      onClick={() => run({ type: 'class', cls })}
                    >
                      {i + 1} {CLASS_STYLES[cls].label}
                    </button>
                  ))}
                </div>
              )}
              <label className={styles.note}>
                Note
                <input type="text" value={note} onChange={(e) => setNote(e.target.value)} />
              </label>
              <div className={styles.buttons}>
                <label>
                  <input type="checkbox" checked={autoAdvance} onChange={(e) => setAutoAdvance(e.target.checked)} />{' '}
                  Auto-advance
                </label>
                <button type="button" onClick={() => run({ type: 'skip' })}>
                  Skip (S)
                </button>
                <button type="button" onClick={() => run({ type: 'prev' })}>
                  ‹ Prev (P)
                </button>
                <button type="button" onClick={() => run({ type: 'next' })}>
                  Next (N) ›
                </button>
                <button type="button" onClick={() => run({ type: 'undo' })}>
                  Undo (Z)
                </button>
              </div>
            </section>
          </section>
        ) : (
          <section className={styles.evidence}>
            <p>Select a detection to review.</p>
          </section>
        )}
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>Review queue{survey ? ` — ${survey.name}` : ''}</h1>
        {surveys && surveys.length > 1 && (
          <label>
            Survey{' '}
            <select
              value={surveyId ?? ''}
              onChange={(e) => {
                setSurveyId(e.target.value);
                navigate(`/review/${encodeURIComponent(e.target.value)}`, { replace: true });
              }}
            >
              {surveys.map((s) => (
                <option key={s.survey_id} value={s.survey_id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <fieldset className={styles.tiers}>
          <legend>Show</legend>
          {REVIEW_TIERS.map((tier) => (
            <label key={tier}>
              <input type="checkbox" checked={tiers.includes(tier)} onChange={() => toggleTier(tier)} /> {TIER_NAMES[tier]}
            </label>
          ))}
        </fieldset>
        {items !== null && total > 0 && (
          <>
            <span aria-live="polite">
              {done.length} of {total} done
            </span>
            <progress max={total} value={done.length} aria-label="Review progress" />
          </>
        )}
      </header>
      {body}
      <p className={styles.keys}>
        Keys: C confirm · R reject, then 1–5 reason · K reclassify, then 1–6 class · S skip · N/P next/previous · Z
        undo (10 s) · Esc cancel
      </p>
    </div>
  );
}
