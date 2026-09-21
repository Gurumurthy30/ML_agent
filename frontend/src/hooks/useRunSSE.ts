import { useState, useEffect, useRef, useCallback } from 'react';
import { PipelineEvent } from '../types/event';

export interface UseRunSSEResult {
  events: PipelineEvent[];
  isConnected: boolean;
  isReconnecting: boolean;
  lastSeq: number;
  error: string | null;
  clearEvents: () => void;
}

export function useRunSSE(runId: string | null): UseRunSSEResult {
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isReconnecting, setIsReconnecting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const lastSeqRef = useRef<number>(0);
  const eventSourceRef = useRef<EventSource | null>(null);
  const retryTimeoutRef = useRef<any>(null);
  const retryAttemptsRef = useRef<number>(0);
  const isMountedRef = useRef<boolean>(true);

  const clearEvents = useCallback(() => {
    setEvents([]);
    lastSeqRef.current = 0;
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    lastSeqRef.current = 0;
    setEvents([]);
    setError(null);
    retryAttemptsRef.current = 0;

    if (!runId) {
      setIsConnected(false);
      setIsReconnecting(false);
      return;
    }

    const connect = () => {
      if (!isMountedRef.current || !runId) return;

      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }

      const sinceSeq = lastSeqRef.current;
      const sseUrl = `/runs/${encodeURIComponent(runId)}/events?since_seq=${sinceSeq}&live=true`;
      
      const es = new EventSource(sseUrl);
      eventSourceRef.current = es;

      es.onopen = () => {
        if (!isMountedRef.current) return;
        setIsConnected(true);
        setIsReconnecting(false);
        setError(null);
        retryAttemptsRef.current = 0;
      };

      es.onmessage = (e) => {
        if (!isMountedRef.current) return;
        try {
          const parsed = JSON.parse(e.data) as PipelineEvent;
          const seq = parsed.seq ?? 0;
          if (seq > lastSeqRef.current) {
            lastSeqRef.current = seq;
          }
          setEvents((prev) => {
            // Avoid duplicate events if replayed
            if (prev.some((existing) => existing.seq === parsed.seq && existing.seq !== undefined)) {
              return prev;
            }
            return [...prev, parsed];
          });
        } catch (err) {
          console.error("Failed parsing SSE event data:", err, e.data);
        }
      };

      es.onerror = () => {
        if (!isMountedRef.current) return;
        es.close();
        eventSourceRef.current = null;
        setIsConnected(false);
        setIsReconnecting(true);

        // Exponential backoff: 1s, 2s, 4s, capped at 10s
        const backoffMs = Math.min(1000 * Math.pow(2, retryAttemptsRef.current), 10000);
        retryAttemptsRef.current += 1;

        if (retryTimeoutRef.current) {
          clearTimeout(retryTimeoutRef.current);
        }

        retryTimeoutRef.current = setTimeout(() => {
          if (isMountedRef.current && runId) {
            connect();
          }
        }, backoffMs);
      };
    };

    connect();

    return () => {
      isMountedRef.current = false;
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current);
      }
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [runId]);

  return {
    events,
    isConnected,
    isReconnecting,
    lastSeq: lastSeqRef.current,
    error,
    clearEvents,
  };
}
