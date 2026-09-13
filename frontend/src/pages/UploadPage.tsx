import { Link } from 'react-router-dom';

import styles from './Page.module.css';

/** S-01 Upload. File validation and job start arrive with ST-091 (Sprint 4). */
export function UploadPage() {
  return (
    <div className={styles.page}>
      <h1>New analysis</h1>
      <div className={styles.drop} aria-label="File drop area (coming in Sprint 4)">
        <p>
          Drop .xtf, GeoTIFF or waterfall images here.
          <br />
          Upload and validation are built in Sprint 4 (ST-091). Until then, run
          <code> sonarsentinel detect &lt;file&gt; </code> or open the <Link to="/map">live map</Link> with sample
          data.
        </p>
      </div>
    </div>
  );
}
