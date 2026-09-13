import { useEffect, useMemo, useState } from 'react';

import { api, ApiError, type EditableSettings, type HealthInfo, type ModelInfo, type Settings } from '../api/client';
import { resetBasemapCache } from '../settings/basemap';
import {
  editableOf,
  isDirty,
  RUNTIME_OPTIONS,
  serverErrors,
  validateSettings,
  type SettingsErrors,
} from '../settings/settingsModel';
import styles from './SettingsPage.module.css';

const LEAVE_MESSAGE = 'You have unsaved settings. Leave without saving?';

type Section = keyof EditableSettings;

/** S-07 Settings (ST-098): defaults for new jobs, validated client- and server-side. */
export function SettingsPage() {
  const [saved, setSaved] = useState<Settings | null>(null);
  const [form, setForm] = useState<EditableSettings | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [serverIssues, setServerIssues] = useState<SettingsErrors>({});
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const load = async () => {
    setLoadError(null);
    setServerIssues({});
    try {
      const settings = await api.settings();
      setSaved(settings);
      setForm(editableOf(settings));
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err));
    }
  };

  useEffect(() => {
    void load();
    api
      .models()
      .then((page) => setModels(page.items.filter((m) => m.kind === 'detector')))
      .catch(() => undefined);
    api
      .health()
      .then(setHealth)
      .catch(() => undefined);
  }, []);

  const baseline = useMemo(() => (saved ? editableOf(saved) : null), [saved]);
  const dirty = isDirty(form, baseline);
  const errors = useMemo(() => (form ? validateSettings(form, saved?.system) : {}), [form, saved]);
  const allErrors = { ...errors, ...serverIssues };
  const valid = Object.keys(errors).length === 0;

  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    // In-app links: ask before React Router navigates away (BrowserRouter has no blocker API).
    const onClick = (event: MouseEvent) => {
      const anchor = (event.target as HTMLElement | null)?.closest?.('a[href]');
      if (!(anchor instanceof HTMLAnchorElement) || anchor.target === '_blank') return;
      if (anchor.origin !== window.location.origin) return;
      if (!window.confirm(LEAVE_MESSAGE)) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    document.addEventListener('click', onClick, true);
    return () => {
      window.removeEventListener('beforeunload', onBeforeUnload);
      document.removeEventListener('click', onClick, true);
    };
  }, [dirty]);

  if (loadError) {
    return (
      <div className={styles.page}>
        <h1>Settings</h1>
        <p role="alert" className={styles.error}>
          Could not load settings: {loadError}
        </p>
        <button type="button" onClick={() => void load()}>
          Retry
        </button>
      </div>
    );
  }
  if (!form || !saved) {
    return (
      <div className={styles.page}>
        <h1>Settings</h1>
        <p role="status">Loading settings…</p>
      </div>
    );
  }

  const set = <S extends Section, K extends keyof EditableSettings[S]>(section: S, key: K, value: EditableSettings[S][K]) => {
    setServerIssues({});
    setToast(null);
    setForm((prev) => (prev ? { ...prev, [section]: { ...prev[section], [key]: value } } : prev));
  };
  const num = (value: string) => (value.trim() === '' ? Number.NaN : Number(value));
  const fieldError = (key: string) =>
    allErrors[key] ? (
      <span role="alert" className={styles.fieldError}>
        {allErrors[key]}
      </span>
    ) : null;

  const save = async () => {
    setSaving(true);
    setServerIssues({});
    try {
      const result = await api.saveSettings(form);
      setSaved(result);
      setForm(editableOf(result));
      resetBasemapCache();
      setToast('Settings saved — they apply to new jobs');
    } catch (err) {
      if (err instanceof ApiError) setServerIssues(serverErrors(err.message, err.details));
      else setServerIssues({ form: err instanceof Error ? err.message : String(err) });
    } finally {
      setSaving(false);
    }
  };

  const system = saved.system;
  const modelIds = [...new Set([form.detection.model_id, ...models.map((m) => m.id)].filter(Boolean))];

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>Settings</h1>
        <p className={styles.muted}>Changes apply to new jobs. Existing reports keep the configuration they were made with.</p>
      </header>

      <form
        className={styles.form}
        onSubmit={(e) => {
          e.preventDefault();
          if (valid && dirty) void save();
        }}
      >
        <fieldset>
          <legend>Detection &amp; confidence</legend>
          <label>
            Detector model
            <select value={form.detection.model_id} onChange={(e) => set('detection', 'model_id', e.target.value)}>
              {modelIds.map((id) => {
                const info = models.find((m) => m.id === id);
                return (
                  <option key={id} value={id} disabled={info ? !info.available : false}>
                    {id}
                    {info && !info.available ? ' (not installed)' : ''}
                  </option>
                );
              })}
            </select>
          </label>
          <label>
            Runtime
            <select value={form.detection.runtime} onChange={(e) => set('detection', 'runtime', e.target.value)}>
              {RUNTIME_OPTIONS.map((o) => {
                const available = o.value === 'auto' || system.runtimes_available.includes(o.value);
                return (
                  <option key={o.value} value={o.value} disabled={!available}>
                    {o.label}
                    {available ? '' : ' (unavailable)'}
                  </option>
                );
              })}
            </select>
          </label>
          <label>
            Min. raw score
            <input
              type="number"
              step="0.01"
              min={0}
              max={1}
              value={Number.isNaN(form.detection.min_raw_score) ? '' : form.detection.min_raw_score}
              onChange={(e) => set('detection', 'min_raw_score', num(e.target.value))}
            />
            {fieldError('detection.min_raw_score')}
          </label>
          <label className={styles.inline}>
            <input
              type="checkbox"
              checked={form.anomaly.enabled}
              onChange={(e) => set('anomaly', 'enabled', e.target.checked)}
            />
            Anomaly scan enabled
          </label>
          <label>
            Anomaly threshold
            <input
              type="number"
              step="0.01"
              min={0}
              max={1}
              value={Number.isNaN(form.anomaly.threshold) ? '' : form.anomaly.threshold}
              onChange={(e) => set('anomaly', 'threshold', num(e.target.value))}
            />
            {fieldError('anomaly.threshold')}
          </label>
          <div className={styles.tiers} role="group" aria-label="Alert tiers">
            {(['hazard', 'review', 'anomaly'] as const).map((tier) => (
              <label key={tier}>
                {tier.charAt(0).toUpperCase() + tier.slice(1)} tier (%)
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={Number.isNaN(form.tiers[tier]) ? '' : form.tiers[tier]}
                  onChange={(e) => set('tiers', tier, num(e.target.value))}
                />
              </label>
            ))}
            {fieldError('tiers')}
          </div>
          <label>
            Map filter: show confidence ≥ (%)
            <input
              type="number"
              min={0}
              max={100}
              value={Number.isNaN(form.map.min_conf_default) ? '' : form.map.min_conf_default}
              onChange={(e) => set('map', 'min_conf_default', num(e.target.value))}
            />
            {fieldError('map.min_conf_default')}
          </label>
        </fieldset>

        <fieldset>
          <legend>Processing</legend>
          <label>
            Ground resolution (m)
            <input
              type="number"
              step="0.01"
              min={0.01}
              value={Number.isNaN(form.processing.ground_resolution_m) ? '' : form.processing.ground_resolution_m}
              onChange={(e) => set('processing', 'ground_resolution_m', num(e.target.value))}
            />
            {fieldError('processing.ground_resolution_m')}
          </label>
          <label>
            Chunk size (pings)
            <input
              type="number"
              min={1}
              value={Number.isNaN(form.processing.pings_per_chunk) ? '' : form.processing.pings_per_chunk}
              onChange={(e) => set('processing', 'pings_per_chunk', num(e.target.value))}
            />
            {fieldError('processing.pings_per_chunk')}
          </label>
          <label>
            Chunk overlap (pings)
            <input
              type="number"
              min={0}
              value={Number.isNaN(form.processing.overlap_pings) ? '' : form.processing.overlap_pings}
              onChange={(e) => set('processing', 'overlap_pings', num(e.target.value))}
            />
            {fieldError('processing.overlap_pings')}
          </label>
        </fieldset>

        <fieldset>
          <legend>Geo &amp; maps</legend>
          <label>
            Layback
            <select value={form.geo.apply_layback} onChange={(e) => set('geo', 'apply_layback', e.target.value)}>
              <option value="auto">Auto</option>
              <option value="true">Always estimate</option>
              <option value="false">Off</option>
            </select>
          </label>
          <label>
            Cluster radius (m)
            <input
              type="number"
              min={0}
              value={Number.isNaN(form.geo.cluster_radius_m) ? '' : form.geo.cluster_radius_m}
              onChange={(e) => set('geo', 'cluster_radius_m', num(e.target.value))}
            />
            {fieldError('geo.cluster_radius_m')}
          </label>
          <div role="radiogroup" aria-label="Basemap" className={styles.radios}>
            <span>Basemap</span>
            <label className={styles.inline}>
              <input
                type="radio"
                name="basemap"
                checked={form.map.basemap === 'online'}
                onChange={() => set('map', 'basemap', 'online')}
              />
              Online (OpenStreetMap)
            </label>
            <label className={styles.inline}>
              <input
                type="radio"
                name="basemap"
                checked={form.map.basemap === 'offline'}
                disabled={!system.offline_tiles_available}
                onChange={() => set('map', 'basemap', 'offline')}
              />
              Offline (tiles/basemap.mbtiles)
            </label>
            {!system.offline_tiles_available && (
              <span className={styles.muted}>No offline tiles installed on the server</span>
            )}
            {fieldError('map.basemap')}
          </div>
          <div role="radiogroup" aria-label="Coordinates" className={styles.radios}>
            <span>Coordinates</span>
            <label className={styles.inline}>
              <input
                type="radio"
                name="coordinates"
                checked={form.map.coordinates === 'dd'}
                onChange={() => set('map', 'coordinates', 'dd')}
              />
              Decimal degrees
            </label>
            <label className={styles.inline}>
              <input
                type="radio"
                name="coordinates"
                checked={form.map.coordinates === 'dms'}
                onChange={() => set('map', 'coordinates', 'dms')}
              />
              DMS
            </label>
          </div>
        </fieldset>

        <fieldset>
          <legend>System</legend>
          <dl className={styles.system}>
            <dt>Backend</dt>
            <dd>
              {health ? `[ok] v${health.version} · runtime ${health.runtime}` : `v${system.version}`}
            </dd>
            <dt>Data folder</dt>
            <dd className={styles.mono}>{system.data_dir}</dd>
            <dt>Max upload</dt>
            <dd>{system.max_upload_gb} GB</dd>
            <dt>Work files</dt>
            <dd>{system.keep_work_files ? 'Kept (debug)' : 'Deleted after each job'}</dd>
            <dt>Runtimes available</dt>
            <dd>{system.runtimes_available.join(', ') || '—'}</dd>
          </dl>
        </fieldset>

        {allErrors.form && (
          <p role="alert" className={styles.error}>
            {allErrors.form}
          </p>
        )}
        {Object.keys(serverIssues).length > 0 && !serverIssues.form && (
          <ul role="alert" className={styles.error} aria-label="Server validation">
            {Object.entries(serverIssues).map(([field, text]) => (
              <li key={field}>
                {field}: {text}
              </li>
            ))}
          </ul>
        )}
        <div className={styles.actions}>
          {dirty && <span className={styles.muted}>Unsaved changes</span>}
          <button type="button" onClick={() => void load()} disabled={saving}>
            Reset
          </button>
          <button type="submit" disabled={!dirty || !valid || saving}>
            {saving ? 'Saving…' : 'Save changes'}
          </button>
        </div>
        {toast && (
          <p role="status" className={styles.toast}>
            {toast}
          </p>
        )}
      </form>
    </div>
  );
}
