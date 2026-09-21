import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

import { RunControls } from '../components/run/RunControls';
import * as api from '../services/api';

vi.mock('../services/api', () => ({
  pauseRun: vi.fn(),
  unpauseRun: vi.fn(),
  stopRun: vi.fn(),
  escapeRun: vi.fn(),
  getExportUrl: vi.fn((id: string) => `/runs/${id}/export`),
}));

describe('RunControls Component Interaction & State Matrix', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('running status: Pause, Escape, and Stop are enabled; Unpause is not rendered', () => {
    render(
      <RunControls
        runId="run_101"
        status="running"
        onControlTriggered={vi.fn()}
        onOpenCompare={vi.fn()}
      />
    );

    const pauseBtn = screen.getByRole('button', { name: /pause/i });
    const escapeBtn = screen.getByRole('button', { name: /escape loop/i });
    const stopBtn = screen.getByRole('button', { name: /stop run/i });

    expect(pauseBtn).toBeEnabled();
    expect(escapeBtn).toBeEnabled();
    expect(stopBtn).toBeEnabled();
    expect(screen.queryByRole('button', { name: /unpause/i })).not.toBeInTheDocument();
  });

  it('paused status: Unpause is rendered and enabled; Escape is disabled; Stop is enabled', () => {
    render(
      <RunControls
        runId="run_102"
        status="paused"
        onControlTriggered={vi.fn()}
        onOpenCompare={vi.fn()}
      />
    );

    const unpauseBtn = screen.getByRole('button', { name: /unpause/i });
    const escapeBtn = screen.getByRole('button', { name: /escape loop/i });
    const stopBtn = screen.getByRole('button', { name: /stop run/i });

    expect(unpauseBtn).toBeEnabled();
    expect(escapeBtn).toBeDisabled(); // Escape only valid while running
    expect(stopBtn).toBeEnabled();
    expect(screen.queryByRole('button', { name: /^pause$/i })).not.toBeInTheDocument();
  });

  it('completed status: Pause, Escape, and Stop are disabled', () => {
    render(
      <RunControls
        runId="run_103"
        status="completed"
        onControlTriggered={vi.fn()}
        onOpenCompare={vi.fn()}
      />
    );

    const pauseBtn = screen.getByRole('button', { name: /pause/i });
    const escapeBtn = screen.getByRole('button', { name: /escape loop/i });
    const stopBtn = screen.getByRole('button', { name: /stop run/i });

    expect(pauseBtn).toBeDisabled();
    expect(escapeBtn).toBeDisabled();
    expect(stopBtn).toBeDisabled();
  });

  it('stopped status: controls are disabled', () => {
    render(
      <RunControls
        runId="run_104"
        status="stopped"
        onControlTriggered={vi.fn()}
        onOpenCompare={vi.fn()}
      />
    );

    const pauseBtn = screen.getByRole('button', { name: /pause/i });
    const escapeBtn = screen.getByRole('button', { name: /escape loop/i });
    const stopBtn = screen.getByRole('button', { name: /stop run/i });

    expect(pauseBtn).toBeDisabled();
    expect(escapeBtn).toBeDisabled();
    expect(stopBtn).toBeDisabled();
  });

  it('failed status: controls are disabled', () => {
    render(
      <RunControls
        runId="run_105"
        status="failed"
        onControlTriggered={vi.fn()}
        onOpenCompare={vi.fn()}
      />
    );

    const pauseBtn = screen.getByRole('button', { name: /pause/i });
    const escapeBtn = screen.getByRole('button', { name: /escape loop/i });
    const stopBtn = screen.getByRole('button', { name: /stop run/i });

    expect(pauseBtn).toBeDisabled();
    expect(escapeBtn).toBeDisabled();
    expect(stopBtn).toBeDisabled();
  });

  it('triggers pauseRun API and calls onControlTriggered callback', async () => {
    vi.mocked(api.pauseRun).mockResolvedValueOnce({ run_id: 'run_101', control: 'paused' });
    const onTriggered = vi.fn();

    render(
      <RunControls
        runId="run_101"
        status="running"
        onControlTriggered={onTriggered}
        onOpenCompare={vi.fn()}
      />
    );

    const pauseBtn = screen.getByRole('button', { name: /pause/i });
    fireEvent.click(pauseBtn);

    await waitFor(() => {
      expect(api.pauseRun).toHaveBeenCalledWith('run_101');
      expect(onTriggered).toHaveBeenCalled();
    });
  });

  it('triggers unpauseRun API when Unpause button clicked', async () => {
    vi.mocked(api.unpauseRun).mockResolvedValueOnce({ run_id: 'run_102', control: 'unpaused' });
    const onTriggered = vi.fn();

    render(
      <RunControls
        runId="run_102"
        status="paused"
        onControlTriggered={onTriggered}
        onOpenCompare={vi.fn()}
      />
    );

    const unpauseBtn = screen.getByRole('button', { name: /unpause/i });
    fireEvent.click(unpauseBtn);

    await waitFor(() => {
      expect(api.unpauseRun).toHaveBeenCalledWith('run_102');
      expect(onTriggered).toHaveBeenCalled();
    });
  });

  it('triggers escapeRun API and shows escape feedback notice', async () => {
    vi.mocked(api.escapeRun).mockResolvedValueOnce({ run_id: 'run_101', control: 'escaped' });
    const onTriggered = vi.fn();

    render(
      <RunControls
        runId="run_101"
        status="running"
        onControlTriggered={onTriggered}
        onOpenCompare={vi.fn()}
      />
    );

    const escapeBtn = screen.getByRole('button', { name: /escape loop/i });
    fireEvent.click(escapeBtn);

    await waitFor(() => {
      expect(api.escapeRun).toHaveBeenCalledWith('run_101');
      expect(screen.getByText(/⚡ Escape signal sent/i)).toBeInTheDocument();
      expect(onTriggered).toHaveBeenCalled();
    });
  });

  it('triggers stopRun API when Stop button clicked', async () => {
    vi.mocked(api.stopRun).mockResolvedValueOnce({ run_id: 'run_101', control: 'stopped' });
    const onTriggered = vi.fn();

    render(
      <RunControls
        runId="run_101"
        status="running"
        onControlTriggered={onTriggered}
        onOpenCompare={vi.fn()}
      />
    );

    const stopBtn = screen.getByRole('button', { name: /stop run/i });
    fireEvent.click(stopBtn);

    await waitFor(() => {
      expect(api.stopRun).toHaveBeenCalledWith('run_101');
      expect(onTriggered).toHaveBeenCalled();
    });
  });
});
