import type { SurveyListItem, SurveyListQuery } from '../api/client';

/** S-07 history filters (ST-098, docs/wireframes/07-history-settings.md Part A). */
export interface HistoryFilters {
  q: string;
  project: string;
  status: string;
  days: '' | '7' | '30' | '90';
}

export const DEFAULT_HISTORY_FILTERS: HistoryFilters = { q: '', project: '', status: '', days: '' };

export const STATUS_OPTIONS = [
  { value: '', label: 'All' },
  { value: 'completed,completed_with_warnings', label: 'Done' },
  { value: 'queued,running', label: 'Processing' },
  { value: 'failed', label: 'Failed' },
  { value: 'cancelled', label: 'Cancelled' },
] as const;

export const DATE_OPTIONS = [
  { value: '', label: 'Any date' },
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
] as const;

export function historyQuery(filters: HistoryFilters, now: Date = new Date()): SurveyListQuery {
  const query: SurveyListQuery = { limit: 200 };
  if (filters.q.trim()) query.q = filters.q.trim();
  if (filters.project) query.project = filters.project;
  if (filters.status) query.status = filters.status.split(',');
  if (filters.days) {
    const from = new Date(now.getTime() - Number(filters.days) * 86_400_000);
    query.from = from.toISOString().slice(0, 10);
  }
  return query;
}

export function statusOf(item: SurveyListItem): string {
  return item.status ?? item.job.status;
}

export function isRunning(item: SurveyListItem): boolean {
  return ['queued', 'running'].includes(statusOf(item));
}

export function statusLabel(item: SurveyListItem): string {
  const status = statusOf(item);
  const warnings = item.warning_count ? ` (!${item.warning_count})` : '';
  switch (status) {
    case 'completed':
    case 'completed_with_warnings':
      return `[ok] Done${warnings}`;
    case 'queued':
      return 'Queued';
    case 'running':
      return 'Processing';
    case 'failed':
      return '[X] Failed';
    case 'cancelled':
      return 'Stopped';
    default:
      return status;
  }
}

export function hazardCount(item: SurveyListItem): number {
  return Number((item.summary.by_tier as Record<string, number> | undefined)?.hazard ?? 0);
}

export function classCounts(item: SurveyListItem): [string, number][] {
  return Object.entries((item.summary.by_class as Record<string, number> | undefined) ?? {}).filter(([, n]) => n > 0);
}
