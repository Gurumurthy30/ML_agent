import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { ApprovalQueue } from '../components/layout/ApprovalQueue';
import * as api from '../services/api';
import { PipelineRun } from '../types/run';

vi.mock('../services/api', () => ({
  resumeRun: vi.fn(),
}));

describe('ApprovalQueue Component', () => {
  const mockPausedRuns: PipelineRun[] = [
    {
      run_id: 'test_run_approval_1',
      status: 'paused',
      stop_reason: 'human_approval_required',
      dataset_path: 'smoke_data/tiny.csv',
      mode: 'full_pipeline',
      guided_mode: true,
      total_attempts: 1,
      total_tokens_in: 100,
      total_tokens_out: 50,
      total_cost_usd: 0.01,
      duration_s: 12.5,
      error_count: 0,
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders pending paused runs count and details', () => {
    render(
      <ApprovalQueue
        pausedRuns={mockPausedRuns}
        onActionComplete={vi.fn()}
        onSelectRun={vi.fn()}
      />
    );

    expect(screen.getByTestId('pending-count')).toHaveTextContent('1 pending');
    expect(screen.getByText('test_run_approval_1')).toBeInTheDocument();
    expect(screen.getByText('Action Requires Approval')).toBeInTheDocument();
  });

  it('handles "approved" button click and calls resumeRun API', async () => {
    vi.mocked(api.resumeRun).mockResolvedValueOnce({
      run_id: 'test_run_approval_1',
      status: 'resumed',
      decision: 'approved',
    });

    const onCompleteMock = vi.fn();
    render(
      <ApprovalQueue
        pausedRuns={mockPausedRuns}
        onActionComplete={onCompleteMock}
        onSelectRun={vi.fn()}
      />
    );

    const approveBtn = screen.getByRole('button', { name: /approve/i });
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(api.resumeRun).toHaveBeenCalledWith('test_run_approval_1', {
        approval_status: 'approved',
        modifications: undefined,
      });
    });

    await waitFor(() => {
      expect(screen.getByText(/Successfully resumed with verdict: APPROVED/i)).toBeInTheDocument();
    });
  });

  it('handles "modify" flow: shows textarea and submits modification instructions', async () => {
    vi.mocked(api.resumeRun).mockResolvedValueOnce({
      run_id: 'test_run_approval_1',
      status: 'resumed',
      decision: 'modify',
    });

    render(
      <ApprovalQueue
        pausedRuns={mockPausedRuns}
        onActionComplete={vi.fn()}
        onSelectRun={vi.fn()}
      />
    );

    const modifyBtn = screen.getByRole('button', { name: /modify/i });
    fireEvent.click(modifyBtn);

    // Textarea appears
    const textarea = screen.getByTestId('modification-input');
    expect(textarea).toBeInTheDocument();

    fireEvent.change(textarea, { target: { value: 'Keep missing columns intact' } });

    const submitBtn = screen.getByRole('button', { name: /submit modification/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(api.resumeRun).toHaveBeenCalledWith('test_run_approval_1', {
        approval_status: 'modify',
        modifications: 'Keep missing columns intact',
      });
    });
  });

  it('handles "reject" button click and calls resumeRun API', async () => {
    vi.mocked(api.resumeRun).mockResolvedValueOnce({
      run_id: 'test_run_approval_1',
      status: 'resumed',
      decision: 'reject',
    });

    render(
      <ApprovalQueue
        pausedRuns={mockPausedRuns}
        onActionComplete={vi.fn()}
        onSelectRun={vi.fn()}
      />
    );

    const rejectBtn = screen.getByRole('button', { name: /reject/i });
    fireEvent.click(rejectBtn);

    await waitFor(() => {
      expect(api.resumeRun).toHaveBeenCalledWith('test_run_approval_1', {
        approval_status: 'reject',
        modifications: undefined,
      });
    });
  });

  it('displays inline banner when backend returns 409 Conflict (double-resume protection)', async () => {
    const conflictError: any = new Error("Run 'test_run_approval_1' is not currently paused");
    conflictError.status = 409;
    vi.mocked(api.resumeRun).mockRejectedValueOnce(conflictError);

    render(
      <ApprovalQueue
        pausedRuns={mockPausedRuns}
        onActionComplete={vi.fn()}
        onSelectRun={vi.fn()}
      />
    );

    const approveBtn = screen.getByRole('button', { name: /approve/i });
    fireEvent.click(approveBtn);

    await waitFor(() => {
      const banner = screen.getByTestId('approval-error-banner');
      expect(banner).toBeInTheDocument();
      expect(banner).toHaveTextContent(/already resumed elsewhere/i);
    });
  });

  it('displays inline banner when backend returns 400 Bad Request (invalid status)', async () => {
    const badRequestError: any = new Error("Invalid or missing approval_status");
    badRequestError.status = 400;
    vi.mocked(api.resumeRun).mockRejectedValueOnce(badRequestError);

    render(
      <ApprovalQueue
        pausedRuns={mockPausedRuns}
        onActionComplete={vi.fn()}
        onSelectRun={vi.fn()}
      />
    );

    const approveBtn = screen.getByRole('button', { name: /approve/i });
    fireEvent.click(approveBtn);

    await waitFor(() => {
      const banner = screen.getByTestId('approval-error-banner');
      expect(banner).toBeInTheDocument();
      expect(banner).toHaveTextContent(/Invalid approval request/i);
    });
  });
});
