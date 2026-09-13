import { Navigate, Route, Routes } from 'react-router-dom';

import { AppBar } from './components/AppBar';
import styles from './App.module.css';
import { HistoryPage } from './pages/HistoryPage';
import { LiveMapPage } from './pages/LiveMapPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { PlaceholderPage } from './pages/PlaceholderPage';
import { ReportsPage } from './pages/ReportsPage';
import { UploadPage } from './pages/UploadPage';

/** Routes follow the wireframe screen inventory (docs/wireframes/README.md §1). */
export function App() {
  return (
    <div className={styles.shell}>
      <a className={styles.skip} href="#main">
        Skip to content
      </a>
      <AppBar />
      <main id="main" className={styles.main}>
        <Routes>
          <Route path="/" element={<Navigate to="/upload" replace />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/map" element={<LiveMapPage />} />
          <Route path="/map/:surveyId" element={<LiveMapPage />} />
          <Route
            path="/review"
            element={<PlaceholderPage screen="S-05" title="Review queue" sprint="Sprint 6 (ST-096)" />}
          />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route
            path="/settings"
            element={<PlaceholderPage screen="S-07" title="Settings" sprint="Sprint 6 (ST-098)" />}
          />
          <Route
            path="/help"
            element={<PlaceholderPage screen="—" title="Help" sprint="see docs/guides/USER_MANUAL.md" />}
          />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </main>
    </div>
  );
}
