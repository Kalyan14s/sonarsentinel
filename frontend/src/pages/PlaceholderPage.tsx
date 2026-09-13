import styles from './Page.module.css';

interface PlaceholderPageProps {
  screen: string;
  title: string;
  sprint: string;
}

/** Screens that exist in the navigation but are built in a later sprint. */
export function PlaceholderPage({ screen, title, sprint }: PlaceholderPageProps) {
  return (
    <div className={styles.page}>
      <h1>{title}</h1>
      <p>
        Screen {screen} is planned for {sprint}. See the <a href="https://github.com/Kalyan14s/sonarsentinel/tree/main/docs/wireframes">wireframes</a>.
      </p>
    </div>
  );
}
