import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { json, makeDetection } from '../test/fixtures';
import { DetectionDrawer } from './DetectionDrawer';

const detection = makeDetection(3, {
  confidence: 87.4,
  alert_tier: 'hazard',
  position: { lat: 13.08412, lon: 80.31275, depth_m: 18.5, uncertainty_m: 4.2 },
  dimensions: { length_m: 6.2, width_m: 3.1, area_m2: 14.8, height_m: 0.4 },
  scores: {
    detector: 0.81,
    anomaly: 0.92,
    shadow: 0.64,
    fp_filter: 0.88,
    persistence: 0.5,
    dropout_penalty: 0.2,
    motion_penalty: 0,
    fused: 0.78,
  },
  quality_flags: ['DROPOUT'],
});

function renderDrawer(overrides: Partial<Parameters<typeof DetectionDrawer>[0]> = {}) {
  const props = {
    detection,
    index: 2,
    total: 7,
    onPrev: vi.fn(),
    onNext: vi.fn(),
    onClose: vi.fn(),
    onReviewed: vi.fn(),
    ...overrides,
  };
  render(<DetectionDrawer {...props} />);
  return props;
}

describe('S-03 detection detail drawer (ST-094)', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('shows values identical to the exported detection (TC-UI-005)', () => {
    renderDrawer();
    expect(screen.getByText('13.084120')).toBeInTheDocument();
    expect(screen.getByText('13° 05\' 02.83" N')).toBeInTheDocument();
    expect(screen.getByText('80.312750')).toBeInTheDocument();
    expect(screen.getByText('80° 18\' 45.90" E')).toBeInTheDocument();
    expect(screen.getByText('6.2 m × 3.1 m')).toBeInTheDocument();
    expect(screen.getByText('14.8 m²')).toBeInTheDocument();
    expect(screen.getByText('~0.4 m')).toBeInTheDocument();
    expect(screen.getByText('± 4.2 m')).toBeInTheDocument();
    expect(screen.getByText('87.4%')).toBeInTheDocument();
    expect(screen.getByText('Why 87%?')).toBeInTheDocument();
    expect(screen.getByText('Fused 0.78 → calibrated 87.4%')).toBeInTheDocument();
    expect(screen.getByText('Quality penalties: dropout −0.20')).toBeInTheDocument();
    expect(screen.getByText('0.81')).toBeInTheDocument();
    expect(screen.getByText('0.50 (1 view)')).toBeInTheDocument();
    expect(screen.getByText('SRV-20260913-001-D0003')).toBeInTheDocument();
    expect(screen.getByText('D3 · 3 of 7')).toBeInTheDocument();
    expect(screen.getByTitle('Part of this object lies on missing sonar data')).toHaveTextContent('DROPOUT');
  });

  it('copies "lat, lon" and shows a toast (TC-UI-006)', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    renderDrawer();
    fireEvent.click(screen.getByRole('button', { name: 'Copy coordinates' }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Copied 13.084120, 80.312750'));
    expect(writeText).toHaveBeenCalledWith('13.084120, 80.312750');
  });

  it('blocks a rejection without a reason, then sends the PATCH', async () => {
    const updated = {
      ...detection,
      review: { status: 'rejected' as const, reviewer: 'analyst-02', reject_reason: 'rock' as const, note: null, updated_utc: null },
    };
    const fetchMock = vi.fn().mockResolvedValue(json(updated));
    vi.stubGlobal('fetch', fetchMock);
    const props = renderDrawer();
    fireEvent.click(screen.getByRole('button', { name: 'Reject' }));
    const submit = screen.getByRole('button', { name: 'Submit rejection' });
    expect(submit).toBeDisabled();
    fireEvent.click(submit);
    expect(fetchMock).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText('Reason (required)'), { target: { value: 'rock' } });
    fireEvent.click(screen.getByRole('button', { name: 'Submit rejection' }));
    await waitFor(() => expect(props.onReviewed).toHaveBeenCalledWith(updated));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/v1/detections/SRV-20260913-001-D0003');
    expect(init.method).toBe('PATCH');
    expect(JSON.parse(String(init.body))).toMatchObject({ review_status: 'rejected', reject_reason: 'rock' });
  });

  it('shows review errors inline', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ error: { code: 'VALIDATION_ERROR', message: 'bad', details: {} } }, 400)));
    renderDrawer();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Review failed: bad'));
  });

  it('offers a retry when the chip is missing', () => {
    renderDrawer();
    const chip = screen.getByRole('img', { name: /Sonar chip of D3 with mask overlay/ });
    expect(chip).toHaveAttribute('src', '/api/v1/detections/SRV-20260913-001-D0003/chip.png?overlay=mask');
    fireEvent.error(chip);
    expect(screen.getByText('Preview not generated')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(screen.getByRole('img', { name: /Sonar chip/ }).getAttribute('src')).toContain('&retry=1');
    fireEvent.click(screen.getByLabelText('Shadow'));
    expect(screen.getByRole('img', { name: /shadow overlay/ }).getAttribute('src')).toContain('overlay=shadow');
  });

  it('shows the pixel box for a detection without GPS', () => {
    renderDrawer({
      detection: makeDetection(4, {
        position: { lat: null, lon: null, depth_m: null, uncertainty_m: null },
        quality_flags: ['NOT_GEOTAGGED'],
        sonar_ref: { source_file: 'harbour_03.png', side: 'n/a', pixel_bbox: [1204, 830, 1266, 861] },
      }),
    });
    expect(screen.getByText('[!] No GPS for this image')).toBeInTheDocument();
    expect(screen.getByText(/Pixel box x 1204–1266, y 830–/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Copy coordinates' })).not.toBeInTheDocument();
  });
});
