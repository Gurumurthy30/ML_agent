import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';

import { PipelineFlowTab } from '../components/tabs/PipelineFlowTab';
import { FeaturePlanTab } from '../components/tabs/FeaturePlanTab';
import { LeaderboardTab } from '../components/tabs/LeaderboardTab';
import { JudgeTab } from '../components/tabs/JudgeTab';
import { LogsTab } from '../components/tabs/LogsTab';
import { ErrorsTab } from '../components/tabs/ErrorsTab';
import { ReportTab } from '../components/tabs/ReportTab';
import { DebugTab } from '../components/tabs/DebugTab';
import { DatasetTab } from '../components/tabs/DatasetTab';

import { PipelineRun } from '../types/run';
import { PipelineEvent } from '../types/event';
import { ModelAttempt } from '../types/attempt';
import { ErrorGroup } from '../types/error';
import * as api from '../services/api';

vi.mock('../services/api', () => ({
  getDatasetPreview: vi.fn(),
  getExportUrl: vi.fn((id: string) => `/runs/${id}/export`),
}));

describe('Tabs Smoke Tests', () => {
  const mockRun: PipelineRun = {
    run_id: 'test_run_smoke_123',
    status: 'running',
    dataset_path: 'data/sample.csv',
    mode: 'full_pipeline',
    guided_mode: false,
    total_attempts: 2,
    total_tokens_in: 1500,
    total_tokens_out: 800,
    total_cost_usd: 0.024,
    duration_s: 45.2,
    error_count: 1,
    best_score: 0.912,
    metric_name: 'f1',
    tags: ['smoke', 'test'],
  };

  const mockEvents: PipelineEvent[] = [
    {
      seq: 1,
      run_id: 'test_run_smoke_123',
      ts: '2026-09-21T10:00:00Z',
      agent: 'profiler',
      event: 'completed',
      phase: 'profiler',
    },
    {
      seq: 2,
      run_id: 'test_run_smoke_123',
      ts: '2026-09-21T10:01:00Z',
      agent: 'features_agent',
      event: 'hard_block',
      phase: 'features',
      feature_plan: {
        description: 'Drop correlated feature and one-hot encode categoricals',
        code: 'df = df.drop(columns=["col_x"])',
        proposed_output_path: 'artifacts/features/test.parquet',
        structural_diff: {
          dropped_columns: ['col_x'],
          added_columns: ['col_x_enc'],
          row_count_delta: 0,
        },
      },
    },
    {
      seq: 3,
      run_id: 'test_run_smoke_123',
      ts: '2026-09-21T10:02:00Z',
      agent: 'modeler_agent',
      event: 'iteration_result',
      phase: 'modeler',
      metric_value: 0.912,
      decision: 'RandomForestClassifier',
      reason: 'Validation improved',
    },
    {
      seq: 4,
      run_id: 'test_run_smoke_123',
      ts: '2026-09-21T10:03:00Z',
      agent: 'judge_agent',
      event: 'verdict',
      phase: 'judge',
      decision: 'accept',
      reason: 'Score surpassed convergence threshold',
    },
    {
      seq: 5,
      run_id: 'test_run_smoke_123',
      ts: '2026-09-21T10:04:00Z',
      agent: 'reporter_agent',
      event: 'report_generated',
      phase: 'reporter',
      report: '# Final Pipeline Summary\nModel performed well on test holdout.',
    },
  ];

  const mockAttempts: ModelAttempt[] = [
    {
      attempt: 1,
      tier: 0,
      agent: 'modeler_agent',
      model_name: 'LogisticRegression',
      cv_score: 0.825,
      cv_score_str: '0.8250',
      delta: null,
      delta_str: '-',
      decision: 'Baseline model',
      reason: 'Initial attempt',
      duration_ms: 1200,
      has_code: true,
      has_diff: false,
      has_error: false,
      ts: '2026-09-21T10:02:00Z',
    },
    {
      attempt: 2,
      tier: 0,
      agent: 'modeler_agent',
      model_name: 'RandomForestClassifier',
      cv_score: 0.912,
      cv_score_str: '0.9120',
      delta: 0.087,
      delta_str: '+0.0870',
      decision: 'Ensemble model',
      reason: 'Hyperparameters tuned',
      duration_ms: 2400,
      has_code: true,
      has_diff: true,
      has_error: false,
      ts: '2026-09-21T10:02:30Z',
    },
  ];

  const mockErrors: ErrorGroup[] = [
    {
      error_signature: 'KeyError: target',
      count: 1,
      agent: 'coder_agent',
      first_seen: '2026-09-21T10:01:15Z',
      last_seen: '2026-09-21T10:01:15Z',
      message: 'KeyError: "target" column missing during feature encoding',
      traceback: 'Traceback (most recent call last):\n  File "exec.py", line 12, in <module>\nKeyError: target',
      consecutive_repeat: false,
    },
  ];

  it('renders PipelineFlowTab without throwing', () => {
    render(<PipelineFlowTab events={mockEvents} isLive={true} status="running" />);
    expect(screen.getByText('Executed Pipeline Sequence')).toBeInTheDocument();
  });

  it('renders FeaturePlanTab with feature plan diff', () => {
    render(<FeaturePlanTab events={mockEvents} />);
    expect(screen.getByText('Feature Engineering & Approval Plan')).toBeInTheDocument();
    expect(screen.getByText('Drop correlated feature and one-hot encode categoricals')).toBeInTheDocument();
  });

  it('renders LeaderboardTab with attempts', () => {
    render(
      <LeaderboardTab
        attempts={mockAttempts}
        metricName="f1"
        bestMetric={0.912}
      />
    );
    expect(screen.getByText('Model Leaderboard')).toBeInTheDocument();
    expect(screen.getByText('RandomForestClassifier')).toBeInTheDocument();
  });

  it('renders JudgeTab with evaluation events', () => {
    render(<JudgeTab events={mockEvents} />);
    expect(screen.getByText('Judge Agent Evaluation & Verdict')).toBeInTheDocument();
  });

  it('renders LogsTab with event stream', () => {
    render(<LogsTab events={mockEvents} />);
    expect(screen.getByText('Hierarchical Event & Execution Logs')).toBeInTheDocument();
  });

  it('renders ErrorsTab with grouped error signatures', () => {
    render(<ErrorsTab errors={mockErrors} />);
    expect(screen.getByText('Aggregated Pipeline Errors')).toBeInTheDocument();
    expect(screen.getByText('KeyError: target')).toBeInTheDocument();
  });

  it('renders ReportTab with generated report or event summary', () => {
    render(<ReportTab run={mockRun} events={mockEvents} />);
    expect(screen.getByText('Executive Pipeline Report')).toBeInTheDocument();
  });

  it('renders DebugTab with state snapshot telemetry', () => {
    render(<DebugTab run={mockRun} events={mockEvents} />);
    expect(screen.getByText('Diagnostics & State Debugger')).toBeInTheDocument();
    expect(screen.getByText('SQLite Run Metadata Record')).toBeInTheDocument();
  });

  it('renders DatasetTab and displays columns and preview rows', async () => {
    vi.mocked(api.getDatasetPreview).mockResolvedValueOnce({
      run_id: 'test_run_smoke_123',
      dataset_path: 'data/sample.csv',
      is_transformed: false,
      columns: ['feature_1', 'feature_2', 'target'],
      total_rows: 100,
      total_columns: 3,
      preview_rows: [
        { feature_1: 1.5, feature_2: 'cat', target: 1 },
        { feature_1: 2.8, feature_2: 'dog', target: 0 },
      ],
    });

    render(<DatasetTab run={mockRun} />);
    expect(screen.getByTestId('dataset-tab')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('feature_1')).toBeInTheDocument();
      expect(screen.getByText('feature_2')).toBeInTheDocument();
      expect(screen.getByText('target')).toBeInTheDocument();
      expect(screen.getByText('Original (Source)')).toBeInTheDocument();
    });
  });
});
