import { Link } from 'react-router-dom';

import styles from './Page.module.css';

export function NotFoundPage() {
  return (
    <div className={styles.page}>
      <h1>Page not found</h1>
      <p>
        <Link to="/upload">Go to Upload</Link>
      </p>
    </div>
  );
}
