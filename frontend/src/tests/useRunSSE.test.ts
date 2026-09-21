import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useRunSSE } from '../hooks/useRunSSE';

class MockEventSource {
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((event: any) => void) | null = null;
  onerror: (() => void) | null = null;
  readyState: number = 0;

  static instances: MockEventSource[] = [];

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
    setTimeout(() => {
      if (this.onopen) this.onopen();
    }, 10);
  }

  close() {
    this.readyState = 2;
  }

  // Helper to simulate receiving SSE message
  emitMessage(data: any) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(data) });
    }
  }

  // Helper to simulate connection drop
  emitError() {
    if (this.onerror) {
      this.onerror();
    }
  }
}

describe('useRunSSE Hook', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    MockEventSource.instances = [];
    (global as any).EventSource = MockEventSource;
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('connects to SSE endpoint with since_seq=0 initially', async () => {
    const { result } = renderHook(() => useRunSSE('run_test_1'));

    expect(MockEventSource.instances.length).toBe(1);
    expect(MockEventSource.instances[0].url).toContain('/runs/run_test_1/events?since_seq=0&live=true');

    // Advance time for onopen
    act(() => {
      vi.advanceTimersByTime(20);
    });

    expect(result.current.isConnected).toBe(true);
    expect(result.current.isReconnecting).toBe(false);
  });

  it('receives events and updates lastSeq monotonically', async () => {
    const { result } = renderHook(() => useRunSSE('run_test_1'));

    act(() => {
      vi.advanceTimersByTime(20);
    });

    const es = MockEventSource.instances[0];

    // Emit first event (seq 1)
    act(() => {
      es.emitMessage({ seq: 1, agent: 'profiler', event_type: 'step_end' });
    });

    expect(result.current.events.length).toBe(1);
    expect(result.current.events[0].seq).toBe(1);

    // Emit second event (seq 5)
    act(() => {
      es.emitMessage({ seq: 5, agent: 'features_agent', event_type: 'step_end' });
    });

    expect(result.current.events.length).toBe(2);
    expect(result.current.events[1].seq).toBe(5);
  });

  it('reconnects with lastSeq after connection drop (no gap, no full replay)', async () => {
    const { result } = renderHook(() => useRunSSE('run_test_1'));

    act(() => {
      vi.advanceTimersByTime(20);
    });

    const es1 = MockEventSource.instances[0];

    // Receive event up to seq 14
    act(() => {
      es1.emitMessage({ seq: 14, agent: 'modeler_agent', event_type: 'attempt_result' });
    });

    expect(result.current.events.length).toBe(1);

    // Connection drops
    act(() => {
      es1.emitError();
    });

    expect(result.current.isConnected).toBe(false);
    expect(result.current.isReconnecting).toBe(true);

    // Fast-forward backoff delay (1000ms)
    act(() => {
      vi.advanceTimersByTime(1100);
    });

    // Reconnection created with since_seq=14!
    expect(MockEventSource.instances.length).toBe(2);
    const es2 = MockEventSource.instances[1];
    expect(es2.url).toContain('/runs/run_test_1/events?since_seq=14&live=true');

    // Onopen on reconnected socket
    act(() => {
      vi.advanceTimersByTime(20);
    });

    expect(result.current.isConnected).toBe(true);
    expect(result.current.isReconnecting).toBe(false);
  });
});
