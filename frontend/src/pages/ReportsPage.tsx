import { useEffect, useState } from 'react';

import { api, type SurveySummary } from '../api/client';
import styles from './Page.module.css';

/** S-06 Reports & Export (JSON and CSV now; GeoJSON/KML with ST-072). */
export function ReportsPage() {
  const [surveys, setSurveys] = useState<SurveySummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .surveys()
      .then((page) => setSurveys(page.items))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  return (
    <div className={styles.page}>
      <h1>Reports</h1>
      {error && <p role="alert">{error}</p>}
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">Survey</th>
            <th scope="col">Detections</th>
            <th scope="col">Downloads</th>
          </tr>
        </thead>
        <tbody>
          {surveys.map((s) => (
            <tr key={s.survey_id}>
              <td>{s.name}</td>
              <td>{s.summary.total_detections}</td>
              <td>
                <a href={api.reportUrl(s.survey_id, 'json')}>JSON</a> · <a href={api.reportUrl(s.survey_id, 'csv')}>CSV</a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
