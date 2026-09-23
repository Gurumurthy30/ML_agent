import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

import { Header } from '../components/layout/Header';
import { RunHeader } from '../components/run/RunHeader';
import { LogsTab } from '../components/tabs/LogsTab';
import { PipelineRun } from '../types/run';
import { PipelineEvent } from '../types/event';

describe('Dark Theme & Header Toggle', () => {
  it('renders theme toggle and calls onToggleDark when clicked', () => {
    const onToggleDark = vi.fn();
    render(
      <Header
        onNewRun={vi.fn()}
        onRefresh={vi.fn()}
        connectedRunsCount={1}
        isDark={true}
        onToggleDark={onToggleDark}
      />
    );

    const toggleButton = screen.getByRole('button', { name: /toggle theme/i });
    expect(toggleButton).toBeInTheDocument();
    expect(screen.getByText('Light')).toBeInTheDocument();

    fireEvent.click(toggleButton);
    expect(onToggleDark).toHaveBeenCalledTimes(1);
  });
});

describe('RunHeader Error Notification Banner', () => {
  const baseRun: PipelineRun = {
    run_id: 'test_failed_run_456',
    status: 'failed',
    stop_reason: 'crashed',
    dataset_path: 'data/train.parquet',
    mode: 'full_pipeline',
    guided_mode: false,
    total_attempts: 1,
    total_tokens_in: 500,
    total_tokens_out: 200,
    total_cost_usd: 0.005,
    duration_s: 12.4,
    error_count: 1,
  };

  it('renders error notification banner when run is failed', () => {
    const onSelectTab = vi.fn();
    render(
      <RunHeader
        run={baseRun}
        onRefresh={vi.fn()}
        onOpenCompare={vi.fn()}
        isConnectedLive={false}
        isReconnecting={false}
        onSelectTab={onSelectTab}
        errorsCount={1}
      />
    );

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText(/Execution Failure Alert/i)).toBeInTheDocument();
    expect(screen.getByText(/Reason: crashed/i)).toBeInTheDocument();
    expect(screen.getByText(/Execution crashed due to an unhandled exception/i)).toBeInTheDocument();

    // Clicking inspect logs calls onSelectTab('logs')
    const inspectBtn = screen.getByRole('button', { name: /Inspect Logs & LLM Texts/i });
    fireEvent.click(inspectBtn);
    expect(onSelectTab).toHaveBeenCalledWith('logs');

    // Dismissing banner
    const dismissBtn = screen.getByTitle('Dismiss alert banner');
    fireEvent.click(dismissBtn);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});

describe('LogsTab Model Text Reader View', () => {
  const mockEvents: PipelineEvent[] = [
    {
      seq: 1,
      run_id: 'test_run',
      ts: '2026-09-23T12:00:00Z',
      agent: 'modeler_agent',
      event_type: 'loop_decision',
      task_spec: 'Train a LightGBMClassifier with 5-fold StratifiedKFold CV and hyperparameter tuning.',
      reason: 'Tree-based gradient boosted models have high inductive bias on tabular tabular datasets.',
    },
    {
      seq: 2,
      run_id: 'test_run',
      ts: '2026-09-23T12:01:00Z',
      agent: 'coder_agent',
      event_type: 'code_execution',
      code: 'import lightgbm as lgb\nmodel = lgb.LGBMClassifier(n_estimators=100)\nmodel.fit(X, y)',
      intent: 'Generate LightGBM baseline script',
      attempt: 1,
    },
    {
      seq: 3,
      run_id: 'test_run',
      ts: '2026-09-23T12:02:00Z',
      agent: 'judge_agent',
      event_type: 'verdict',
      decision: 'accept',
      feedback: 'Model achieved CV score 0.8842, successfully exceeding threshold without overfitting.',
      reason: 'Solid generalizability observed across test splits.',
    },
    {
      seq: 4,
      run_id: 'test_run',
      ts: '2026-09-23T12:03:00Z',
      agent: 'reporter_agent',
      event_type: 'report_written',
      report: '# Autonomous Machine Learning Summary\nLightGBM delivered best performance on tabular benchmark.',
    },
  ];

  it('allows switching to Model Text Reader and reading full LLM outputs', () => {
    render(<LogsTab events={mockEvents} />);

    // Initially in Hierarchy Event Tree view
    expect(screen.getByText('Hierarchical Event & Execution Logs')).toBeInTheDocument();

    // Switch to Model Text Reader
    const readerToggle = screen.getByRole('button', { name: /Model Text Reader/i });
    fireEvent.click(readerToggle);

    // Verify all model texts are rendered
    expect(screen.getByText(/Executive ML Report Written by Reporter Model/i)).toBeInTheDocument();
    expect(screen.getByText(/Autonomous Machine Learning Summary/i)).toBeInTheDocument();
    expect(screen.getByText(/Quality Verdict & Feedback/i)).toBeInTheDocument();
    expect(screen.getByText(/Model achieved CV score 0.8842/i)).toBeInTheDocument();
    expect(screen.getByText(/Train a LightGBMClassifier with 5-fold StratifiedKFold/i)).toBeInTheDocument();
    expect(screen.getByText(/import lightgbm as lgb/i)).toBeInTheDocument();
  });

  it('filters model text items by search query', () => {
    render(<LogsTab events={mockEvents} />);

    const readerToggle = screen.getByRole('button', { name: /Model Text Reader/i });
    fireEvent.click(readerToggle);

    const searchInput = screen.getByPlaceholderText(/Search model text, code, feedback.../i);
    fireEvent.change(searchInput, { target: { value: 'LightGBMClassifier' } });

    // Modeler spec matches
    expect(screen.getByText(/Train a LightGBMClassifier with 5-fold StratifiedKFold/i)).toBeInTheDocument();
    // Judge feedback shouldn't match
    expect(screen.queryByText(/Model achieved CV score 0.8842/i)).not.toBeInTheDocument();
  });
});
