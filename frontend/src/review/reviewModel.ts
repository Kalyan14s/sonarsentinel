import { REJECT_REASONS, type Detection, type RejectReason, type ReviewRequest } from '../api/client';
import { ALL_CLASSES } from '../dashboard/filters';

/** S-05 review queue (ST-096, docs/wireframes/05-review-queue.md). */
export const REVIEW_TIERS = ['review', 'anomaly', 'hazard'] as const;
export type ReviewTier = (typeof REVIEW_TIERS)[number];
export const DEFAULT_TIERS: ReviewTier[] = ['review', 'anomaly'];
export const UNDO_WINDOW_MS = 10_000;

export type DecisionMode = 'idle' | 'reject' | 'reclassify';

export type KeyAction =
  | { type: 'confirm' }
  | { type: 'reject-mode' }
  | { type: 'reclassify-mode' }
  | { type: 'reason'; reason: RejectReason }
  | { type: 'class'; cls: string }
  | { type: 'skip' }
  | { type: 'next' }
  | { type: 'prev' }
  | { type: 'undo' }
  | { type: 'cancel' };

/**
 * Keyboard map: C confirm · R reject then 1–5 reason · K reclassify then 1–6 class · S skip ·
 * N/P next/previous · Z undo · Esc leaves reject/reclassify mode.
 */
export function keyAction(key: string, mode: DecisionMode, currentClass: string | undefined): KeyAction | null {
  if (key === 'Escape') return mode === 'idle' ? null : { type: 'cancel' };
  if (mode !== 'idle' && /^[1-9]$/.test(key)) {
    const index = Number(key) - 1;
    if (mode === 'reject') {
      const reason = REJECT_REASONS[index];
      return reason ? { type: 'reason', reason } : null;
    }
    const cls = ALL_CLASSES[index];
    return cls && cls !== currentClass ? { type: 'class', cls } : null;
  }
  switch (key.toLowerCase()) {
    case 'c':
      return { type: 'confirm' };
    case 'r':
      return { type: 'reject-mode' };
    case 'k':
      return { type: 'reclassify-mode' };
    case 's':
      return { type: 'skip' };
    case 'n':
      return { type: 'next' };
    case 'p':
      return { type: 'prev' };
    case 'z':
      return { type: 'undo' };
    default:
      return null;
  }
}

export function isPending(d: Detection): boolean {
  return d.review.status === 'pending';
}

/** The next pending item after `fromId` in queue order, wrapping to the start; null when none are left. */
export function nextPendingId(items: readonly Detection[], fromId: string | null): string | null {
  const start = fromId === null ? -1 : items.findIndex((d) => d.detection_id === fromId);
  for (let step = 1; step <= items.length; step += 1) {
    const candidate = items[(start + step + items.length) % items.length];
    if (candidate && isPending(candidate) && candidate.detection_id !== fromId) return candidate.detection_id;
  }
  return null;
}

/** Move within the pending items; a reopened (already reviewed) item moves to the first pending one. */
export function movePending(items: readonly Detection[], currentId: string | null, delta: number): string | null {
  const pending = items.filter(isPending);
  if (pending.length === 0) return currentId;
  const index = pending.findIndex((d) => d.detection_id === currentId);
  if (index < 0) return pending[0]?.detection_id ?? null;
  const next = Math.min(Math.max(index + delta, 0), pending.length - 1);
  return pending[next]?.detection_id ?? currentId;
}

/** Local optimistic copy of a detection after a decision. */
export function applyDecision(d: Detection, body: ReviewRequest): Detection {
  return {
    ...d,
    class: (body.class ?? d.class) as Detection['class'],
    review: {
      ...d.review,
      status: body.review_status,
      reject_reason: body.review_status === 'rejected' ? (body.reject_reason ?? null) : null,
      note: body.note ?? d.review.note ?? null,
    },
  };
}

/** Plain-language summary of the score breakdown (wireframe: "Why 62%: …"). */
export function whyText(d: Detection): string {
  const s = d.scores;
  const parts = [`detector ${s.detector.toFixed(2)}`];
  if (s.shadow !== undefined) parts.push(`shadow ${s.shadow.toFixed(2)}`);
  if (s.fp_filter !== undefined) parts.push(`FP filter ${s.fp_filter.toFixed(2)}`);
  if (s.anomaly !== undefined) parts.push(`anomaly ${s.anomaly.toFixed(2)}`);
  const notes: string[] = [];
  if (s.shadow !== undefined) notes.push(s.shadow >= 0.5 ? 'shadow consistent with a raised object' : 'weak or no shadow');
  if (s.fp_filter !== undefined && s.fp_filter < 0.5) notes.push('false-positive filter doubts it');
  if (s.anomaly !== undefined && s.anomaly >= 0.5) notes.push('unusual compared with normal seabed');
  if ((s.dropout_penalty ?? 0) > 0) notes.push('overlaps missing sonar data');
  if ((s.motion_penalty ?? 0) > 0) notes.push('towfish motion was high');
  return `Why ${Math.round(d.confidence)}%: ${parts.join(' · ')}${notes.length ? ` — ${notes.join('; ')}` : ''}`;
}

export function summarizeDecisions(items: readonly Detection[]): {
  reviewed: number;
  confirmed: number;
  rejected: number;
  reclassified: number;
} {
  const count = (status: string) => items.filter((d) => d.review.status === status).length;
  const confirmed = count('confirmed');
  const rejected = count('rejected');
  const reclassified = count('reclassified');
  return { reviewed: confirmed + rejected + reclassified, confirmed, rejected, reclassified };
}
