import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';

import { api, subscribeToJob, type Detection, type JobEvent, type SurveySummary } from '../api/client';
import { Workspace } from '../components/Workspace';
import { MapView } from '../map/MapView';
import { CLASS_STYLES, TIER_LABELS, type AlertTier, type DetectionClass } from '../tokens';
import styles from './LiveMapPage.module.css';

/** S-02 Live Map: track, detections and a replay of the processing events. */
export function LiveMapPage() {
  const params = useParams();
  const [survey, setSurvey] = useState<SurveySummary | null>(null);
  const [track, setTrack] = useState<[number, number][]>([]);
  const [detections, setDetections] = useState<Detection[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [progress, setProgress] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const id = params.surveyId ?? (await api.surveys()).items[0]?.survey_id;
        if (!id) {
          setError('No surveys yet. Upload a sonar file to start.');
          return;
        }
        const [summary, line, list] = await Promise.all([
          api.survey(id),
          api.track(id),
          api.detections(id, { sort: '-confidence', limit: 500 }),
        ]);
        if (cancelled) return;
        setSurvey(summary);
        setTrack(line.features[0]?.geometry.coordinates.map(([lon, lat]) => [lat, lon]) ?? []);
        setDetections(list.items);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [params.surveyId]);

  const replay = useCallback(() => {
    if (!survey) return;
    setTrack([]);
    setDetections([]);
    const unsubscribe = subscribeToJob(survey.job.job_id, (event: JobEvent) => {
      if (event.type === 'progress') setProgress(`${event.stage} ${event.percent.toFixed(0)}%`);
      if (event.type === 'track') setTrack((prev) => [...prev, ...event.points]);
      if (event.type === 'detection') setDetections((prev) => [...prev, event.detection]);
      if (event.type === 'done') {
        setProgress(event.status);
        unsubscribe();
      }
    });
  }, [survey]);

  const selectedDetection = useMemo(
    () => detections.find((d) => d.detection_id === selected) ?? null,
    [detections, selected],
  );

  return (
    <Workspace
      context={
        <>
          <strong>{survey?.name ?? 'Live map'}</strong>
          {survey && <span>Job {survey.job.status}</span>}
          {progress && <span aria-live="polite">{progress}</span>}
          <button type="button" onClick={replay} disabled={!survey} className={styles.button}>
            Replay processing
          </button>
        </>
      }
      left={
        <section aria-label="Legend">
          <h2 className={styles.heading}>Classes</h2>
          <ul className={styles.legend}>
            {Object.entries(CLASS_STYLES).map(([key, style]) => (
              <li key={key}>
                <span className={styles.swatch} style={{ background: style.color }} aria-hidden />
                {style.label}
              </li>
            ))}
          </ul>
        </section>
      }
      right={
        <section aria-label="Detections">
          <h2 className={styles.heading}>Detections ({detections.length})</h2>
          {error && <p role="alert">{error}</p>}
          <ol className={styles.list}>
            {detections.map((d) => (
              <li key={d.detection_id}>
                <button
                  type="button"
                  className={d.detection_id === selected ? `${styles.row} ${styles.selected}` : styles.row}
                  onClick={() => setSelected(d.detection_id)}
                >
                  <span className={styles.swatch} style={{ background: CLASS_STYLES[d.class as DetectionClass].color }} />
                  <span>{CLASS_STYLES[d.class as DetectionClass].label}</span>
                  <span className={styles.conf}>{d.confidence.toFixed(1)}%</span>
                  <span className={styles.tier}>{TIER_LABELS[d.alert_tier as AlertTier]}</span>
                </button>
              </li>
            ))}
          </ol>
          {selectedDetection && (
            <dl className={styles.detail}>
              <dt>ID</dt>
              <dd>{selectedDetection.detection_id}</dd>
              <dt>Position</dt>
              <dd className={styles.mono}>
                {selectedDetection.position.lat?.toFixed(6) ?? '—'}, {selectedDetection.position.lon?.toFixed(6) ?? '—'}
              </dd>
              <dt>Size</dt>
              <dd>
                {selectedDetection.dimensions.length_m ?? '—'} × {selectedDetection.dimensions.width_m ?? '—'} m
              </dd>
              <dt>Flags</dt>
              <dd>{selectedDetection.quality_flags.join(', ') || 'none'}</dd>
            </dl>
          )}
        </section>
      }
      status={
        survey && (
          <>
            <span>{survey.summary.total_detections} detections</span>
            <span>{survey.track_length_km ?? '—'} km track</span>
            <a href={api.reportUrl(survey.survey_id, 'csv')}>Download CSV</a>
          </>
        )
      }
    >
      <MapView track={track} detections={detections} selectedId={selected} onSelect={setSelected} />
    </Workspace>
  );
}
