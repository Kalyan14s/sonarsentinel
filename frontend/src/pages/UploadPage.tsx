import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { ApiError, api, createSurvey, validateSurvey, type UploadProgress } from '../api/client';
import {
  ACCEPT,
  badgeFor,
  checkNavHeader,
  describeFile,
  fileProgress,
  formatBytes,
  hasCrsWarning,
  isNavCsv,
  isValidRow,
  loadAdvancedOpen,
  loadOptions,
  localFileProblem,
  navTemplateCsv,
  needsNavigation,
  saveAdvancedOpen,
  saveOptions,
  startBlockers,
  toSurveyOptions,
  validEpsg,
  type AdvancedOptions,
  type FileRow,
} from '../upload/uploadModel';
import styles from './UploadPage.module.css';

const RESOLUTIONS = [0.05, 0.1, 0.2, 0.25, 0.5];

function detailList(details: Record<string, unknown>, ...keys: string[]): string[] {
  for (const key of keys) {
    const value = details[key];
    if (Array.isArray(value)) return value.map(String);
  }
  return [];
}

function downloadTemplate(): void {
  if (typeof URL.createObjectURL !== 'function') return;
  const url = URL.createObjectURL(new Blob([navTemplateCsv()], { type: 'text/csv' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'sonarsentinel_nav_template.csv';
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/** S-01 Upload / New analysis (ST-091, docs/wireframes/01-upload.md). */
export function UploadPage() {
  const navigate = useNavigate();
  const nextId = useRef(1);
  const inputRef = useRef<HTMLInputElement>(null);
  const navInputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const [rows, setRows] = useState<FileRow[]>([]);
  const [dragging, setDragging] = useState(false);
  const [offline, setOffline] = useState(false);
  const [navCsv, setNavCsv] = useState<File | null>(null);
  const [navErrors, setNavErrors] = useState<string[]>([]);
  const [allowNoGps, setAllowNoGps] = useState(false);
  const [searchParams] = useSearchParams();
  // Re-run / Fix from History (S-07) prefill the survey name; uploads themselves cannot be re-sent.
  const [options, setOptions] = useState<AdvancedOptions>(() => {
    const loaded = loadOptions();
    const name = searchParams.get('name');
    return name ? { ...loaded, name } : loaded;
  });
  const [advancedOpen, setAdvancedOpen] = useState(() => loadAdvancedOpen());
  const [models, setModels] = useState<string[]>([]);
  const [upload, setUpload] = useState<UploadProgress | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => saveOptions(options), [options]);
  useEffect(() => saveAdvancedOpen(advancedOpen), [advancedOpen]);

  useEffect(() => {
    let active = true;
    api
      .models()
      .then((result) => {
        if (active) setModels(result.items.filter((m) => m.available).map((m) => m.id));
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  const updateRow = (id: number, patch: Partial<FileRow>) =>
    setRows((prev) => prev.map((row) => (row.id === id ? { ...row, ...patch } : row)));

  const validateRow = useCallback(async (row: FileRow) => {
    try {
      const response = await validateSurvey([row.file]);
      const result = response.files.find((f) => f.filename === row.file.name) ?? response.files[0];
      setOffline(false);
      if (!result) {
        updateRow(row.id, { status: 'error', error: 'The server returned no result for this file' });
        return;
      }
      updateRow(row.id, {
        status: 'done',
        result: { ...result, warnings: result.warnings ?? [] },
        error: result.valid ? undefined : (result.warnings?.[0] ?? 'File could not be read'),
      });
    } catch (err) {
      if (err instanceof ApiError) {
        setOffline(false);
        if (err.code === 'CRS_REQUIRED') {
          // Readable file with projected coordinates: usable once a UTM zone is chosen.
          updateRow(row.id, {
            status: 'done',
            result: {
              filename: row.file.name,
              valid: true,
              format: row.file.name.toLowerCase().endsWith('.xtf') ? 'xtf' : 'geotiff',
              has_navigation: true,
              warnings: [`CRS_REQUIRED: ${err.message}`],
            },
          });
          return;
        }
        updateRow(row.id, { status: 'error', error: err.message, errorCode: err.code });
      } else {
        setOffline(true);
        updateRow(row.id, { status: 'offline' });
      }
    }
  }, []);

  const attachNav = useCallback(async (file: File) => {
    setNavCsv(file);
    setAllowNoGps(false);
    const missing = await checkNavHeader(file);
    setNavErrors(missing.length ? [`${file.name} is missing required columns: ${missing.join(', ')}`] : []);
  }, []);

  const addFiles = useCallback(
    (files: File[]) => {
      const added: FileRow[] = [];
      for (const file of files) {
        if (isNavCsv(file.name)) {
          void attachNav(file);
          continue;
        }
        const problem = localFileProblem(file);
        added.push({
          id: nextId.current++,
          file,
          status: problem ? 'error' : 'validating',
          error: problem?.message,
          errorCode: problem?.code,
        });
      }
      if (!added.length) return;
      setRows((prev) => [...prev, ...added]);
      for (const row of added) if (row.status === 'validating') void validateRow(row);
    },
    [attachNav, validateRow],
  );

  const validRows = useMemo(() => rows.filter(isValidRow), [rows]);
  const navAccepted = Boolean(navCsv) && navErrors.length === 0;
  const epsgRequired = rows.some((row) => hasCrsWarning(row.result));
  const epsgMissing = epsgRequired && !validEpsg(options);
  const blockers = startBlockers(rows, navAccepted, allowNoGps, epsgMissing);
  const uploading = upload !== null;
  const firstNoGpsId = validRows.find((row) => needsNavigation(row.result))?.id;

  useEffect(() => {
    if (epsgRequired) setAdvancedOpen(true);
  }, [epsgRequired]);

  const setOption = <K extends keyof AdvancedOptions>(key: K, value: AdvancedOptions[K]) =>
    setOptions((prev) => ({ ...prev, [key]: value }));

  const onPick = (event: ChangeEvent<HTMLInputElement>) => {
    addFiles(Array.from(event.target.files ?? []));
    event.target.value = '';
  };

  const onPickNav = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) void attachNav(file);
    event.target.value = '';
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    addFiles(Array.from(event.dataTransfer.files));
  };

  const retry = () => {
    for (const row of rows) {
      if (row.status !== 'offline') continue;
      updateRow(row.id, { status: 'validating' });
      void validateRow(row);
    }
    if (!rows.some((row) => row.status === 'offline')) setOffline(false);
  };

  const cancel = () => {
    if (abortRef.current) {
      abortRef.current.abort();
      return;
    }
    setRows([]);
    setNavCsv(null);
    setNavErrors([]);
    setAllowNoGps(false);
    setSubmitError(null);
  };

  const start = async () => {
    if (blockers.length || uploading) return;
    const files = validRows.map((row) => row.file);
    const controller = new AbortController();
    abortRef.current = controller;
    setSubmitError(null);
    setUpload({ loaded: 0, total: files.reduce((sum, f) => sum + f.size, 0) + (navCsv?.size ?? 0) });
    try {
      const created = await createSurvey(
        files,
        navAccepted ? navCsv : null,
        toSurveyOptions(options, allowNoGps && !navAccepted),
        { signal: controller.signal, onProgress: setUpload },
      );
      abortRef.current = null;
      navigate(
        `/map/${encodeURIComponent(created.survey_id)}?job=${encodeURIComponent(created.job_id)}` +
          `&min_conf=${options.minShownPercent}`,
      );
    } catch (err) {
      abortRef.current = null;
      setUpload(null);
      if (err instanceof DOMException && err.name === 'AbortError') {
        setSubmitError('Upload cancelled.');
      } else if (err instanceof ApiError) {
        if (err.status === 0) setOffline(true);
        if (err.code === 'NAV_CSV_INVALID') {
          const missing = detailList(err.details, 'missing', 'columns');
          setNavErrors([missing.length ? `${err.message} (${missing.join(', ')})` : err.message]);
        }
        setSubmitError(err.message);
      } else {
        setSubmitError(err instanceof Error ? err.message : String(err));
      }
    }
  };

  const sizes = validRows.map((row) => row.file.size);

  return (
    <div className={styles.page}>
      <h1>New analysis</h1>
      <p className={styles.lead}>
        Upload a raw side-scan sonar log. Detections will appear on the map as they are found.
      </p>

      {offline && (
        <div role="alert" className={styles.banner}>
          <span>Backend not reachable — check that the service is running.</span>
          <button type="button" className={styles.button} onClick={retry}>
            Retry
          </button>
        </div>
      )}

      <div className={styles.top}>
        <div
          className={dragging ? `${styles.drop} ${styles.dragging}` : styles.drop}
          data-testid="drop-zone"
          onDragEnter={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <p className={styles.dropTitle}>Drag &amp; drop sonar files here</p>
          <p>
            or{' '}
            <button type="button" className={styles.button} onClick={() => inputRef.current?.click()}>
              Browse files
            </button>
          </p>
          <p className={styles.hint}>.xtf .tif .png .jpg .csv (max 2 GB per file)</p>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={ACCEPT}
            className={styles.visuallyHidden}
            aria-label="Choose sonar files"
            onChange={onPick}
          />
        </div>

        <aside className={styles.panel} aria-label="Supported inputs">
          <h2 className={styles.heading}>Supported inputs</h2>
          <ul className={styles.inputs}>
            <li>
              <span className={styles.ok}>ok</span> .xtf — GPS in pings
            </li>
            <li>
              <span className={styles.ok}>ok</span> .tif — GeoTIFF mosaic
            </li>
            <li>
              <span className={styles.ok}>ok</span> .png / .jpg + nav .csv
            </li>
            <li>
              <span className={styles.muted}>not supported</span> .jsf .sl2 .sl3
            </li>
          </ul>
          <button type="button" className={styles.button} onClick={downloadTemplate}>
            Download nav CSV template
          </button>
          <Link to="/map" className={styles.link}>
            Try a sample survey
          </Link>
        </aside>
      </div>

      <input
        ref={navInputRef}
        type="file"
        accept=".csv,text/csv"
        className={styles.visuallyHidden}
        aria-label="Attach navigation CSV"
        onChange={onPickNav}
      />

      {rows.length > 0 && (
        <section aria-label="Files" className={styles.section}>
          <h2 className={styles.heading}>Files ({rows.length})</h2>
          <ul className={styles.files}>
            {rows.map((row) => {
              const badge = badgeFor(row);
              const uploadIndex = validRows.findIndex((valid) => valid.id === row.id);
              return (
                <li
                  key={row.id}
                  data-testid="file-row"
                  className={badge?.kind === 'error' ? `${styles.fileRow} ${styles.fileError}` : styles.fileRow}
                >
                  <span className={styles.name}>{row.file.name}</span>
                  <span className={styles.size}>{formatBytes(row.file.size)}</span>
                  <span className={styles.info}>
                    {row.status === 'validating' && (
                      <span role="status" className={styles.spinner}>
                        Reading header…
                      </span>
                    )}
                    {row.status === 'offline' && 'Not checked (backend offline)'}
                    {row.status !== 'validating' && row.status !== 'offline' && (row.error ?? (row.result ? describeFile(row.result) : ''))}
                  </span>
                  {badge ? (
                    <span className={`${styles.badge} ${styles[badge.kind] ?? ''}`}>{badge.label}</span>
                  ) : (
                    <span />
                  )}
                  <button
                    type="button"
                    className={styles.remove}
                    aria-label={`Remove ${row.file.name}`}
                    disabled={uploading}
                    onClick={() => setRows((prev) => prev.filter((r) => r.id !== row.id))}
                  >
                    ×
                  </button>
                  {upload && uploadIndex >= 0 && (
                    <progress
                      className={styles.progress}
                      max={1}
                      value={fileProgress(upload.loaded, sizes, uploadIndex)}
                      aria-label={`Upload progress for ${row.file.name}`}
                    />
                  )}
                  {row.id === firstNoGpsId && (
                    <div className={styles.navAttach}>
                      <span>Attach navigation CSV:</span>
                      <button type="button" className={styles.button} onClick={() => navInputRef.current?.click()}>
                        Choose .csv
                      </button>
                      <span>or</span>
                      <button
                        type="button"
                        className={styles.button}
                        aria-pressed={allowNoGps}
                        onClick={() => setAllowNoGps(true)}
                      >
                        Continue without GPS
                      </button>
                      {navCsv && (
                        <span className={navAccepted ? styles.okText : styles.errorText}>
                          {navCsv.name}
                          {navAccepted ? ' — columns OK' : ''}
                        </span>
                      )}
                      {navErrors.map((message) => (
                        <p key={message} role="alert" className={styles.errorText}>
                          {message} —{' '}
                          <button type="button" className={styles.linkButton} onClick={downloadTemplate}>
                            download the template
                          </button>
                        </p>
                      ))}
                      {allowNoGps && !navAccepted && (
                        <p className={styles.note}>Results will have pixel coordinates only.</p>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <details
        className={styles.advanced}
        open={advancedOpen}
        onToggle={(event) => setAdvancedOpen(event.currentTarget.open)}
      >
        <summary>Advanced options</summary>
        <div className={styles.grid}>
          <label className={styles.field}>
            Survey name
            <input value={options.name} onChange={(e) => setOption('name', e.target.value)} />
          </label>
          <label className={styles.field}>
            Project
            <input value={options.project} onChange={(e) => setOption('project', e.target.value)} />
          </label>
          <fieldset className={epsgMissing ? `${styles.fieldset} ${styles.required}` : styles.fieldset}>
            <legend>Coordinates</legend>
            <label>
              <input
                type="radio"
                name="coordinates"
                checked={options.coordinates === 'auto'}
                onChange={() => setOption('coordinates', 'auto')}
              />{' '}
              Auto-detect
            </label>
            <label>
              <input
                type="radio"
                name="coordinates"
                checked={options.coordinates === 'utm'}
                onChange={() => setOption('coordinates', 'utm')}
              />{' '}
              UTM EPSG
            </label>
            <input
              aria-label="UTM EPSG code"
              inputMode="numeric"
              placeholder="e.g. 32644"
              required={epsgRequired}
              value={options.utmEpsg}
              onChange={(e) => {
                setOption('utmEpsg', e.target.value);
                setOption('coordinates', 'utm');
              }}
            />
            {epsgMissing && <p className={styles.errorText}>Projected coordinates: enter the UTM EPSG code.</p>}
          </fieldset>
          <label className={styles.field}>
            Resolution (m/px)
            <select
              value={options.groundResolution}
              onChange={(e) => setOption('groundResolution', Number(e.target.value))}
            >
              {RESOLUTIONS.map((r) => (
                <option key={r} value={r}>
                  {r.toFixed(2)}
                </option>
              ))}
            </select>
          </label>
          <fieldset className={styles.fieldset}>
            <legend>Layback</legend>
            {(['auto', 'off', 'manual'] as const).map((value) => (
              <label key={value}>
                <input
                  type="radio"
                  name="layback"
                  checked={options.layback === value}
                  onChange={() => setOption('layback', value)}
                />{' '}
                {value === 'auto' ? 'Auto' : value === 'off' ? 'Off' : 'Manual'}
              </label>
            ))}
            <input
              aria-label="Manual layback (m)"
              type="number"
              min={0}
              step={0.1}
              disabled={options.layback !== 'manual'}
              value={options.manualLaybackM ?? ''}
              onChange={(e) => setOption('manualLaybackM', e.target.value === '' ? null : Number(e.target.value))}
            />
          </fieldset>
          <label className={styles.field}>
            Model
            <select value={options.detectorModel} onChange={(e) => setOption('detectorModel', e.target.value)}>
              <option value="">Default (auto)</option>
              {models.map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.check}>
            <input
              type="checkbox"
              checked={options.anomalyScan}
              onChange={(e) => setOption('anomalyScan', e.target.checked)}
            />{' '}
            Scan for ghost nets and unknown objects
          </label>
          <label className={styles.field}>
            Min. shown (%)
            <input
              type="number"
              min={0}
              max={100}
              step={5}
              value={options.minShownPercent}
              onChange={(e) => setOption('minShownPercent', Number(e.target.value))}
            />
          </label>
        </div>
      </details>

      {upload && (
        <div className={styles.total}>
          <progress max={upload.total || 1} value={upload.loaded} aria-label="Total upload progress" />
          <span>
            {formatBytes(upload.loaded)} of {formatBytes(upload.total)}
          </span>
        </div>
      )}
      {submitError && (
        <p role="alert" className={styles.errorText}>
          {submitError}
        </p>
      )}

      <div className={styles.actions}>
        {!uploading && blockers[0] && <p className={styles.hint}>{blockers[0]}</p>}
        <button
          type="button"
          className={styles.button}
          onClick={cancel}
          disabled={!uploading && rows.length === 0 && !navCsv}
        >
          Cancel
        </button>
        <button
          type="button"
          className={styles.primary}
          onClick={() => void start()}
          disabled={blockers.length > 0 || uploading}
        >
          Start analysis
        </button>
      </div>
    </div>
  );
}
