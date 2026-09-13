import type { ReactNode } from 'react';

import styles from './Workspace.module.css';

interface WorkspaceProps {
  context?: ReactNode;
  left?: ReactNode;
  right?: ReactNode;
  status?: ReactNode;
  children: ReactNode;
}

/** Context bar, left panel, main area, right panel and status bar (wireframes §3). */
export function Workspace({ context, left, right, status, children }: WorkspaceProps) {
  return (
    <div className={styles.workspace}>
      {context && <div className={styles.context}>{context}</div>}
      <div className={styles.columns}>
        {left && (
          <aside className={styles.left} aria-label="Filters and layers">
            {left}
          </aside>
        )}
        <section className={styles.center}>{children}</section>
        {right && (
          <aside className={styles.right} aria-label="Details">
            {right}
          </aside>
        )}
      </div>
      {status && (
        <footer className={styles.status} role="status">
          {status}
        </footer>
      )}
    </div>
  );
}
