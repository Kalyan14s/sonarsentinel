import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { api, type SurveySummary } from '../api/client';
import styles from './Page.module.css';

/** S-07 Survey history (search, filters and delete arrive with ST-098). */
export function HistoryPage() {
  const [surveys, setSurveys] = useState<SurveySummary[] | null>(null);

  useEffect(() => {
    api
      .surveys()
      .then((page) => setSurveys(page.items))
      .catch(() => setSurveys([]));
  }, []);

  return (
    <div className={styles.page}>
      <h1>Survey history</h1>
      {surveys === null && <p>Loading…</p>}
      {surveys?.length === 0 && (
        <p>
          No surveys yet. <Link to="/upload">Upload a file</Link>.
        </p>
      )}
      {surveys && surveys.length > 0 && (
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Status</th>
              <th scope="col">Track</th>
              <th scope="col">Detections</th>
            </tr>
          </thead>
          <tbody>
            {surveys.map((s) => (
              <tr key={s.survey_id}>
                <td>
                  <Link to={`/map/${encodeURIComponent(s.survey_id)}`}>{s.name}</Link>
                </td>
                <td>{s.job.status}</td>
                <td>{s.track_length_km ?? '—'} km</td>
                <td>{s.summary.total_detections}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
