import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';

import {
  api,
  REPORT_FORMATS,
  subscribeToJob,
  type ConnectionStatus,
  type Detection,
  type MosaicInfo,
  type SurveySummary,
} from '../api/client';
import { Workspace } from '../components/Workspace';
import { DetectionDrawer } from '../dashboard/DetectionDrawer';
import { DetectionList } from '../dashboard/DetectionList';
import { FilterPanel } from '../dashboard/FilterPanel';
import {
  ALL_TIERS,
  countDetections,
  DEFAULT_FILTERS,
  filterAndSort,
  filtersFromSearch,
  filtersToSearch,
  type Filters,
} from '../dashboard/filters';
import { PixelView } from '../dashboard/PixelView';
import {
  INITIAL_STATE,
  isActive,
  liveReducer,
  qualitySegmentsOf,
  statusFrom,
  trackPointsOf,
  warningPoints,
  type WarningItem,
} from '../dashboard/store';
import { MapView, type MapController } from '../map/MapView';
import styles from './LiveMapPage.module.css';

const FORMAT_LABELS = { json: 'JSON', csv: 'CSV', geojson: 'GeoJSON', kml: 'KML' } as const;

function formatEta(seconds: number | null): string | null {
  if (seconds === null || !Number.isFinite(seconds)) return null;
  const s = Math.max(0, Math.round(seconds));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return ['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(target.tagName) || target.isContentEditable;
}

/**
 * S-02 Live Map (ST-092/093) with the S-03 drawer (ST-094). With `?job=<job_id>`, or when the
 * survey's job is still running, it follows the job's WebSocket events; otherwise it loads the
 * stored results. Filters live in the URL query string, so a view can be shared.
 */
export function LiveMapPage() {
  const params = useParams();
  const [search, setSearch] = useSearchParams();
  const jobParam = search.get('job');
  const [survey, setSurvey] = useState<SurveySummary | null>(null);
  const [liveJob, setLiveJob] = useState<string | null>(jobParam);
  const [state, dispatch] = useReducer(liveReducer, INITIAL_STATE);
  const [connection, setConnection] = useState<ConnectionStatus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [confirmStop, setConfirmStop] = useState(false);
  const [showWarnings, setShowWarnings] = useState(false);
  const [mosaic, setMosaic] = useState<MosaicInfo | null>(null);
  const controller = useRef<MapController | null>(null);
  const filtersRef = useRef<HTMLElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const filters = useMemo(() => filtersFromSearch(search), [search]);
  const setFilters = useCallback(
    (next: Filters) => setSearch((prev) => filtersToSearch(next, prev), { replace: true }),
    [setSearch],
  );

  useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    setSurvey(null);
    setMosaic(null);
    setLiveJob(jobParam);
    (async () => {
      try {
        const id = params.surveyId ?? (await api.surveys()).items[0]?.survey_id;
        if (!id) {
          if (!jobParam) setLoadError('No surveys yet. Upload a sonar file to start.');
          return;
        }
        const summary = await api.survey(id);
        if (cancelled) return;
        setSurvey(summary);
        setMosaic(summary.mosaic ?? null);
        const live = jobParam ?? (isActive(statusFrom(summary.job.status)) ? summary.job.job_id : null);
        if (live) {
          setLiveJob(live);
          return;
        }
        const [line, list] = await Promise.all([
          api.track(id).catch(() => null),
          api.detections(id, { limit: 5000 }),
        ]);
        if (cancelled) return;
        dispatch({ type: 'loaded', detections: list.items, track: line, status: statusFrom(summary.job.status) });
      } catch (err) {
        if (!cancelled && !jobParam) setLoadError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [params.surveyId, jobParam]);

  useEffect(() => {
    if (!liveJob) return;
    dispatch({ type: 'reset', status: 'queued' });
    return subscribeToJob(
      liveJob,
      (event) => {
        dispatch({ type: 'event', event });
        if (event.type === 'done' && event.mosaic) setMosaic(event.mosaic);
      },
      { onStatus: setConnection },
    );
  }, [liveJob]);

  const all = useMemo(() => Array.from(state.detections.values()), [state.detections]);
  const visible = useMemo(() => filterAndSort(all, filters), [all, filters]);
  const counts = useMemo(() => countDetections(all), [all]);
  const track = useMemo(() => trackPointsOf(state.chunks, state.loadedTrack), [state.chunks, state.loadedTrack]);
  const quality = useMemo(
    () => qualitySegmentsOf(state.chunks, state.warnings, state.loadedQuality),
    [state.chunks, state.warnings, state.loadedQuality],
  );
  const selected = state.selectedId ? (state.detections.get(state.selectedId) ?? null) : null;
  const selectedIndex = visible.findIndex((d) => d.detection_id === state.selectedId);
  const surveyId = survey?.survey_id ?? params.surveyId ?? null;
  const active = isActive(state.status);
  const notGeotagged = all.length
    ? all.every((d) => d.position.lat === null)
    : survey !== null && survey.bbox === null && !active && track.length === 0 && state.status !== 'idle';

  const select = useCallback((id: string | null) => dispatch({ type: 'select', id }), []);
  const openDetection = useCallback(
    (id: string) => {
      select(id);
      setDrawerOpen(true);
    },
    [select],
  );
  const move = useCallback(
    (delta: number) => {
      if (!visible.length) return;
      const index = visible.findIndex((d) => d.detection_id === state.selectedId);
      const next = index < 0 ? (delta > 0 ? 0 : visible.length - 1) : Math.min(Math.max(index + delta, 0), visible.length - 1);
      const target = visible[next];
      if (target) select(target.detection_id);
    },
    [visible, state.selectedId, select],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        if (drawerOpen) {
          setDrawerOpen(false);
          event.preventDefault();
        }
        return;
      }
      if (isTyping(event.target) || event.ctrlKey || event.metaKey || event.altKey) return;
      if (event.key === 'f' || event.key === 'F') {
        filtersRef.current?.querySelector('input')?.focus();
        event.preventDefault();
      } else if (event.key === 'l' || event.key === 'L') {
        listRef.current?.focus();
        event.preventDefault();
      } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        move(event.key === 'ArrowDown' ? 1 : -1);
        event.preventDefault();
      } else if (event.key === 'Enter' && state.selectedId) {
        setDrawerOpen(true);
        event.preventDefault();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [drawerOpen, move, state.selectedId]);

  const zoomToWarning = (warning: WarningItem) => {
    const points = warningPoints(state.chunks, state.loadedQuality, warning);
    if (points.length) controller.current?.zoomToPoints(points);
  };

  const stop = async () => {
    setConfirmStop(false);
    if (!liveJob) return;
    try {
      await api.cancelJob(liveJob);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err));
    }
  };

  const pendingReview = all.filter(
    (d) => d.review.status === 'pending' && (d.alert_tier === 'hazard' || d.alert_tier === 'review'),
  ).length;
  const eta = formatEta(state.etaS);

  let empty: React.ReactNode;
  if (active || state.status === 'idle') {
    empty = state.pingsTotal
      ? `No detections yet — scanning ${state.pingsTotal.toLocaleString('en-US')} pings`
      : 'No detections yet';
  } else if (all.length === 0) {
    empty = (
      <>
        No man-made objects detected above {filters.minConf}% confidence.{' '}
        <button type="button" onClick={() => setFilters({ ...filters, minConf: 0, tiers: ALL_TIERS })}>
          Show low-confidence
        </button>
      </>
    );
  } else {
    empty = (
      <>
        No detections match the filters.{' '}
        <button type="button" onClick={() => setFilters({ ...DEFAULT_FILTERS, sort: filters.sort })}>
          Reset filters
        </button>
      </>
    );
  }

  return (
    <Workspace
      context={
        <div className={styles.context}>
          <strong>{survey?.name ?? 'Live map'}</strong>
          {survey?.source_files?.length ? <span className={styles.muted}>{survey.source_files.join(', ')}</span> : null}
          {connection === 'connecting' && state.lastSeq === 0 && <span>Connecting to job…</span>}
          {active && state.stage && (
            <>
              <progress max={100} value={state.percent ?? 0} aria-label="Processing progress" />
              <span aria-live="polite">
                {Math.round(state.percent ?? 0)}% · {state.stage}
                {eta ? ` · ETA ${eta}` : ''}
              </span>
            </>
          )}
          {active && state.lastSeq > 0 && !state.stage && <span>Reading sonar log…</span>}
          {(state.status === 'completed' || state.status === 'completed_with_warnings') && (
            <span>
              [ok] Completed{survey?.job.duration_s ? ` in ${survey.job.duration_s} s` : ''} ·{' '}
              {state.warnings.length} warning{state.warnings.length === 1 ? '' : 's'}
            </span>
          )}
          {state.status === 'cancelled' && <span>Stopped — detections found so far are kept</span>}
          {pendingReview > 0 && !active && <Link to="/review">Review {pendingReview} items</Link>}
          {active && liveJob && (
            <button type="button" className={styles.button} onClick={() => setConfirmStop(true)}>
              Stop
            </button>
          )}
        </div>
      }
      left={
        <FilterPanel filters={filters} counts={counts} onChange={setFilters} panelRef={filtersRef} />
      }
      right={
        drawerOpen && selected ? (
          <DetectionDrawer
            key={selected.detection_id}
            detection={selected}
            index={selectedIndex < 0 ? 0 : selectedIndex}
            total={visible.length}
            onPrev={() => move(-1)}
            onNext={() => move(1)}
            onClose={() => setDrawerOpen(false)}
            onReviewed={(detection: Detection) => dispatch({ type: 'reviewed', detection })}
            onZoom={(detection) => {
              const { lat, lon } = detection.position;
              if (lat !== null && lon !== null) controller.current?.zoomToPoints([[lat, lon]]);
            }}
          />
        ) : (
          <DetectionList
            detections={visible}
            selectedId={state.selectedId}
            sort={filters.sort}
            onSortChange={(sort) => setFilters({ ...filters, sort })}
            onSelect={openDetection}
            listRef={listRef}
            empty={empty}
          />
        )
      }
      status={
        <div className={styles.status}>
          <span>
            {all.length} detections: {counts.tiers.hazard ?? 0} hazard, {counts.tiers.review ?? 0} review,{' '}
            {counts.tiers.anomaly ?? 0} anomaly
          </span>
          {state.warnings.length > 0 && (
            <button
              type="button"
              className={styles.link}
              aria-expanded={showWarnings}
              onClick={() => setShowWarnings((open) => !open)}
            >
              [!] {state.warnings.length} warning{state.warnings.length === 1 ? '' : 's'}
            </button>
          )}
          {surveyId && (
            <span className={styles.downloads}>
              Reports:
              {REPORT_FORMATS.map((format) =>
                notGeotagged && (format === 'geojson' || format === 'kml') ? (
                  <span key={format} aria-disabled="true" title="Not available without GPS" className={styles.disabled}>
                    {FORMAT_LABELS[format]}
                  </span>
                ) : (
                  <a key={format} href={api.reportUrl(surveyId, format)} download>
                    {FORMAT_LABELS[format]}
                  </a>
                ),
              )}
              <Link to={`/reports?${filtersToSearch(filters, new URLSearchParams({ survey: surveyId })).toString()}`}>
                Export…
              </Link>
            </span>
          )}
          {showWarnings && (
            <ul className={styles.warnings} aria-label="Warnings">
              {state.warnings.map((warning, i) => (
                <li key={`${warning.code}-${warning.ping_start}-${i}`}>
                  <button type="button" className={styles.link} onClick={() => zoomToWarning(warning)}>
                    {warning.code} · pings {warning.ping_start}–{warning.ping_end}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      }
    >
      {connection === 'reconnecting' && (
        <p role="status" className={`${styles.banner} ${styles.info}`}>
          Reconnecting…
        </p>
      )}
      {state.status === 'failed' && (
        <p role="alert" className={`${styles.banner} ${styles.danger}`}>
          Job failed: {state.error?.code ?? 'ERROR'} — {state.error?.message ?? 'processing stopped'}. Partial results
          remain visible.
        </p>
      )}
      {loadError && (
        <p role="alert" className={`${styles.banner} ${styles.danger}`}>
          {loadError}
        </p>
      )}
      {confirmStop && (
        <div role="alertdialog" aria-label="Stop processing" className={styles.dialog}>
          <p>Stop processing? Detections found so far are kept.</p>
          <button type="button" className={styles.button} onClick={() => void stop()}>
            Stop processing
          </button>
          <button type="button" className={styles.button} onClick={() => setConfirmStop(false)}>
            Keep running
          </button>
        </div>
      )}
      {notGeotagged ? (
        <>
          <p role="status" className={`${styles.banner} ${styles.info}`}>
            No GPS — coordinates shown in pixels
          </p>
          <PixelView detections={visible} selectedId={state.selectedId} onSelect={openDetection} />
        </>
      ) : (
        <MapView
          track={track}
          quality={quality}
          mosaic={mosaic}
          detections={visible}
          selected={selected}
          onSelect={openDetection}
          onReady={(c) => {
            controller.current = c;
          }}
        />
      )}
    </Workspace>
  );
}
