import { Navigate, Route, Routes } from 'react-router-dom';

import { AppBar } from './components/AppBar';
import styles from './App.module.css';
import { HistoryPage } from './pages/HistoryPage';
import { LiveMapPage } from './pages/LiveMapPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { PlaceholderPage } from './pages/PlaceholderPage';
import { ReportsPage } from './pages/ReportsPage';
import { ReviewPage } from './pages/ReviewPage';
import { SettingsPage } from './pages/SettingsPage';
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
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/review/:surveyId" element={<ReviewPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/settings" element={<SettingsPage />} />
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
