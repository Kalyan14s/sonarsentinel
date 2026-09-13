import { NavLink } from 'react-router-dom';

import styles from './AppBar.module.css';

export const PRIMARY_NAV = [
  { to: '/upload', label: 'Upload' },
  { to: '/map', label: 'Live Map' },
  { to: '/review', label: 'Review' },
  { to: '/reports', label: 'Reports' },
  { to: '/history', label: 'History' },
] as const;

export const SECONDARY_NAV = [
  { to: '/settings', label: 'Settings' },
  { to: '/help', label: 'Help' },
] as const;

function linkClass({ isActive }: { isActive: boolean }) {
  return isActive ? `${styles.link} ${styles.active}` : styles.link;
}

/** App bar from the global layout (docs/wireframes/README.md §3). */
export function AppBar() {
  return (
    <header className={styles.bar}>
      <span className={styles.logo} aria-label="SonarSentinel">
        SonarSentinel
      </span>
      <nav aria-label="Primary" className={styles.nav}>
        {PRIMARY_NAV.map((item) => (
          <NavLink key={item.to} to={item.to} className={linkClass}>
            {item.label}
          </NavLink>
        ))}
      </nav>
      <nav aria-label="Secondary" className={styles.nav}>
        {SECONDARY_NAV.map((item) => (
          <NavLink key={item.to} to={item.to} className={linkClass}>
            {item.label}
          </NavLink>
        ))}
      </nav>
    </header>
  );
}
