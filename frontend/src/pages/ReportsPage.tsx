import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import {
  api,
  REPORT_FORMATS,
  type ReportFormat,
  type ReportOptions,
  type ReportScope,
  type SurveySummary,
} from '../api/client';
import { filtersFromSearch, toDetectionQuery } from '../dashboard/filters';
import pageStyles from './Page.module.css';
import styles from './ReportsPage.module.css';

const FORMAT_INFO: Record<ReportFormat, { label: string; help: string }> = {
  json: { label: 'JSON', help: 'Full report, schema v1.0' },
  csv: { label: 'CSV', help: 'Spreadsheet, one row per object' },
  geojson: { label: 'GeoJSON', help: 'QGIS / GIS: points and footprints' },
  kml: { label: 'KML', help: 'Google Earth / GPS: placemarks by class' },
};
const GEO_FORMATS: ReportFormat[] = ['geojson', 'kml'];
const PREVIEW_LINES = 12;

/** S-06 Reports & Export (ST-095): format, scope, preview and downloads for one survey. */
export function ReportsPage() {
  const [search, setSearch] = useSearchParams();
  const [surveys, setSurveys] = useState<SurveySummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [formats, setFormats] = useState<ReportFormat[]>(['json', 'csv']);
  const [scope, setScope] = useState<ReportScope>(search.has('min_conf') || search.has('tier') || search.has('class') ? 'filtered' : 'all');
  const [includeRejected, setIncludeRejected] = useState(false);
  const [previewFormat, setPreviewFormat] = useState<ReportFormat>('csv');
  const [preview, setPreview] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  useEffect(() => {
    api
      .surveys()
      .then((page) => setSurveys(page.items))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  const filters = useMemo(() => filtersFromSearch(search), [search]);
  const surveyId = search.get('survey') ?? surveys?.[0]?.survey_id ?? null;
  const survey = surveys?.find((s) => s.survey_id === surveyId) ?? null;
  const geotagged = survey ? survey.bbox !== null : true;
  const selected = formats.filter((f) => geotagged || !GEO_FORMATS.includes(f));
  const shownPreview = selected.includes(previewFormat) ? previewFormat : (selected[0] ?? null);
  const options: ReportOptions = useMemo(
    () => ({ scope, includeRejected, filters: toDetectionQuery(filters) }),
    [scope, includeRejected, filters],
  );
  const previewUrl = survey && shownPreview ? api.reportUrl(survey.survey_id, shownPreview, options) : null;
  const processing = survey ? ['queued', 'running'].includes(survey.job.status) : false;

  useEffect(() => {
    if (!previewUrl) {
      setPreview(null);
      return;
    }
    let cancelled = false;
    setPreviewError(null);
    fetch(previewUrl)
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const text = await response.text();
        if (!cancelled) setPreview(text.split('\n').slice(0, PREVIEW_LINES).join('\n'));
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setPreview(null);
          setPreviewError(err instanceof Error ? err.message : String(err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [previewUrl]);

  const toggleFormat = (format: ReportFormat) =>
    setFormats((current) => (current.includes(format) ? current.filter((f) => f !== format) : [...current, format]));

  return (
    <div className={pageStyles.page}>
      <div className={styles.titleRow}>
        <h1>Reports{survey ? ` — ${survey.name}` : ''}</h1>
        <label className={styles.survey}>
          Survey
          <select
            value={surveyId ?? ''}
            onChange={(e) =>
              setSearch((prev) => {
                const next = new URLSearchParams(prev);
                next.set('survey', e.target.value);
                return next;
              })
            }
          >
            {(surveys ?? []).map((s) => (
              <option key={s.survey_id} value={s.survey_id}>
                {s.survey_id} · {s.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error && <p role="alert">{error}</p>}
      {surveys?.length === 0 && <p>No surveys yet.</p>}
      {processing && (
        <p role="status" className={styles.banner}>
          Survey still processing — the report will include detections found so far (partial).
        </p>
      )}

      {survey && (
        <>
          <section className={styles.section}>
            <h2>1. Format</h2>
            <div className={styles.cards}>
              {REPORT_FORMATS.map((format) => {
                const disabled = !geotagged && GEO_FORMATS.includes(format);
                return (
                  <label
                    key={format}
                    className={disabled ? `${styles.card} ${styles.cardDisabled}` : styles.card}
                    title={disabled ? 'Not available: this survey has no GPS positions' : undefined}
                  >
                    <input
                      type="checkbox"
                      checked={selected.includes(format)}
                      disabled={disabled}
                      onChange={() => toggleFormat(format)}
                    />
                    <strong>{FORMAT_INFO[format].label}</strong>
                    <span>{FORMAT_INFO[format].help}</span>
                  </label>
                );
              })}
            </div>
          </section>

          <div className={styles.columns}>
            <fieldset className={styles.section}>
              <legend>2. Scope</legend>
              {(
                [
                  ['all', `All detections (${survey.summary.total_detections})`],
                  ['filtered', 'Current map filters'],
                  ['hazards', `Hazards only (${survey.summary.by_tier.hazard ?? 0})`],
                  ['confirmed', 'Confirmed only'],
                ] as [ReportScope, string][]
              ).map(([value, text]) => (
                <label key={value} className={styles.option}>
                  <input type="radio" name="scope" checked={scope === value} onChange={() => setScope(value)} />
                  {text}
                </label>
              ))}
            </fieldset>
            <fieldset className={styles.section}>
              <legend>3. Options</legend>
              <label className={styles.option}>
                <input
                  type="checkbox"
                  checked={includeRejected}
                  onChange={(e) => setIncludeRejected(e.target.checked)}
                />
                Include rejected detections
              </label>
            </fieldset>
          </div>

          <section className={styles.section}>
            <h2>4. Preview{shownPreview ? ` (${FORMAT_INFO[shownPreview].label})` : ''}</h2>
            <div className={styles.tabs} role="tablist" aria-label="Preview format">
              {selected.map((format) => (
                <button
                  key={format}
                  type="button"
                  role="tab"
                  aria-selected={format === shownPreview}
                  onClick={() => setPreviewFormat(format)}
                >
                  {FORMAT_INFO[format].label}
                </button>
              ))}
            </div>
            {previewError && <p role="alert">Preview unavailable: {previewError}</p>}
            {preview !== null && (
              <pre className={styles.preview} aria-label="Report preview">
                {preview}
              </pre>
            )}
          </section>

          <section className={styles.section}>
            <h2>Download</h2>
            {selected.length === 0 ? (
              <p>Select at least one format.</p>
            ) : (
              <ul className={styles.files}>
                {selected.map((format) => (
                  <li key={format}>
                    <a href={api.reportUrl(survey.survey_id, format, options)} download>
                      {survey.survey_id}_report.{format}
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className={styles.section}>
            <h2>Previous exports</h2>
            {survey.report_urls && Object.keys(survey.report_urls).length ? (
              <ul className={styles.files}>
                {Object.entries(survey.report_urls).map(([format, url]) => (
                  <li key={format}>
                    <a href={url} download>
                      {format.toUpperCase()} · all detections
                    </a>
                  </li>
                ))}
              </ul>
            ) : (
              <p>No stored exports yet.</p>
            )}
          </section>
        </>
      )}
    </div>
  );
}
