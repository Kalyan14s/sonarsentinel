import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { api, ApiError, type SurveyListItem } from '../api/client';
import {
  classCounts,
  DATE_OPTIONS,
  DEFAULT_HISTORY_FILTERS,
  hazardCount,
  historyQuery,
  isRunning,
  STATUS_OPTIONS,
  statusLabel,
  statusOf,
  type HistoryFilters,
} from '../history/historyModel';
import { CLASS_STYLES, type DetectionClass } from '../tokens';
import { formatBytes } from '../upload/uploadModel';
import styles from './HistoryPage.module.css';

const SEARCH_DEBOUNCE_MS = 300;

function classLabel(cls: string): string {
  return CLASS_STYLES[cls as DetectionClass]?.label ?? cls;
}

/** S-07 Survey history (ST-098): search, filters, open, reports, re-run, delete. */
export function HistoryPage() {
  const navigate = useNavigate();
  const [filters, setFilters] = useState<HistoryFilters>(DEFAULT_HISTORY_FILTERS);
  const [search, setSearch] = useState('');
  const [surveys, setSurveys] = useState<SurveyListItem[] | null>(null);
  const [projects, setProjects] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<SurveyListItem | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setFilters((prev) => (prev.q === search ? prev : { ...prev, q: search })), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [search]);

  const query = useMemo(() => historyQuery(filters), [filters]);

  useEffect(() => {
    let active = true;
    setSurveys(null);
    setError(null);
    api
      .surveys(query)
      .then((page) => {
        if (!active) return;
        setSurveys(page.items);
        setProjects((prev) => {
          const names = new Set(prev);
          for (const item of page.items) if (item.project) names.add(item.project);
          return [...names].sort();
        });
      })
      .catch((err: unknown) => active && setError(err instanceof Error ? err.message : String(err)));
    return () => {
      active = false;
    };
  }, [query]);

  const filtered = filters.q !== '' || filters.project !== '' || filters.status !== '' || filters.days !== '';

  const remove = async (item: SurveyListItem) => {
    setConfirmDelete(null);
    setDeleting(item.survey_id);
    setMessage(null);
    try {
      await api.deleteSurvey(item.survey_id);
      setSurveys((list) => list?.filter((s) => s.survey_id !== item.survey_id) ?? list);
      setMessage(`Deleted ${item.name}`);
    } catch (err) {
      const text =
        err instanceof ApiError && err.code === 'JOB_NOT_CANCELLABLE'
          ? `${item.name} is still processing — cancel the job first (${err.message})`
          : `Could not delete ${item.name}: ${err instanceof Error ? err.message : String(err)}`;
      setMessage(text);
    } finally {
      setDeleting(null);
    }
  };

  const rerun = (item: SurveyListItem) =>
    navigate(`/upload?rerun=${encodeURIComponent(item.survey_id)}&name=${encodeURIComponent(item.name)}`);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>Survey history</h1>
        <Link to="/upload" className={styles.primary}>
          + New analysis
        </Link>
      </header>

      <div className={styles.filters} role="search">
        <label>
          Search
          <input
            type="search"
            value={search}
            placeholder="name, file, project…"
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <label>
          Project
          <select value={filters.project} onChange={(e) => setFilters({ ...filters, project: e.target.value })}>
            <option value="">All</option>
            {projects.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label>
          Status
          <select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}>
            {STATUS_OPTIONS.map((o) => (
              <option key={o.label} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Date
          <select
            value={filters.days}
            onChange={(e) => setFilters({ ...filters, days: e.target.value as HistoryFilters['days'] })}
          >
            {DATE_OPTIONS.map((o) => (
              <option key={o.label} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {message && (
        <p role="status" className={styles.message}>
          {message}
        </p>
      )}
      {error && (
        <p role="alert" className={styles.error}>
          Could not load surveys: {error}
        </p>
      )}

      {confirmDelete && (
        <div role="alertdialog" aria-label="Delete survey" className={styles.dialog}>
          <p>
            Delete <strong>{confirmDelete.name}</strong>? Its uploads, reports, chips and review labels are removed.
          </p>
          <button type="button" className={styles.danger} onClick={() => void remove(confirmDelete)}>
            Delete
          </button>
          <button type="button" onClick={() => setConfirmDelete(null)}>
            Keep
          </button>
        </div>
      )}

      {surveys === null && !error && (
        <table className={styles.table} aria-busy="true" aria-label="Loading surveys">
          <tbody>
            {[0, 1, 2].map((i) => (
              <tr key={i} className={styles.skeleton}>
                <td colSpan={6}>&nbsp;</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {surveys?.length === 0 && (
        <p className={styles.empty}>
          {filtered ? (
            'No surveys match the filters.'
          ) : (
            <>
              No surveys yet. <Link to="/upload">New analysis</Link>
            </>
          )}
        </p>
      )}

      {surveys && surveys.length > 0 && (
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Name / file</th>
              <th scope="col">Date (UTC)</th>
              <th scope="col">Status</th>
              <th scope="col">Detections</th>
              <th scope="col">Hazards</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {surveys.map((s) => {
              const failed = statusOf(s) === 'failed';
              const running = isRunning(s);
              const openHref = `/map/${encodeURIComponent(s.survey_id)}${running ? `?job=${encodeURIComponent(s.job.job_id)}` : ''}`;
              return (
                <tr
                  key={s.survey_id}
                  aria-busy={deleting === s.survey_id}
                  className={deleting === s.survey_id ? styles.deleting : undefined}
                >
                  <td>
                    <strong>{s.name}</strong>
                    <br />
                    <small>
                      {s.source_files.join(', ')}
                      {s.size_bytes ? ` · ${formatBytes(s.size_bytes)}` : ''}
                      {s.project ? ` · ${s.project}` : ''}
                    </small>
                  </td>
                  <td>
                    {s.created_utc.slice(0, 10)}
                    <br />
                    <small>{s.created_utc.slice(11, 16)}</small>
                  </td>
                  <td>
                    {statusLabel(s)}
                    {failed && s.error_code && <div className={styles.code}>{s.error_code}</div>}
                  </td>
                  <td>
                    {classCounts(s).length
                      ? classCounts(s).map(([cls, n]) => (
                          <span key={cls} className={styles.count}>
                            {classLabel(cls)} {n}
                          </span>
                        ))
                      : '—'}
                  </td>
                  <td>{failed ? '—' : hazardCount(s)}</td>
                  <td className={styles.actions}>
                    {failed ? (
                      <Link
                        to={`/upload?fix=${encodeURIComponent(s.survey_id)}&name=${encodeURIComponent(s.name)}${
                          s.error_code ? `&code=${encodeURIComponent(s.error_code)}` : ''
                        }`}
                      >
                        Fix
                      </Link>
                    ) : (
                      <Link to={openHref}>Open</Link>
                    )}
                    <button
                      type="button"
                      aria-haspopup="menu"
                      aria-expanded={menuFor === s.survey_id}
                      aria-label={`More actions for ${s.name}`}
                      onClick={() => setMenuFor(menuFor === s.survey_id ? null : s.survey_id)}
                    >
                      …
                    </button>
                    {menuFor === s.survey_id && (
                      <div role="menu" className={styles.menu}>
                        <button type="button" role="menuitem" onClick={() => rerun(s)}>
                          Re-run
                        </button>
                        <button
                          type="button"
                          role="menuitem"
                          onClick={() => navigate(`/reports?survey=${encodeURIComponent(s.survey_id)}`)}
                        >
                          Reports
                        </button>
                        <button
                          type="button"
                          role="menuitem"
                          className={styles.danger}
                          onClick={() => {
                            setMenuFor(null);
                            setConfirmDelete(s);
                          }}
                        >
                          Delete
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {surveys && surveys.length > 0 && (
        <p className={styles.footer}>
          Showing {surveys.length} survey{surveys.length === 1 ? '' : 's'}
        </p>
      )}
    </div>
  );
}
