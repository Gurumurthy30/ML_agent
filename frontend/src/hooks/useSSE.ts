import { useState, useEffect, useRef } from "react";
import { PipelineEvent } from "../types";

interface UseSSEResult {
  events: PipelineEvent[];
  isConnected: boolean;
  isCompleted: boolean;
  error: string | null;
  clearEvents: () => void;
}

export function useSSE(
  projectId?: string,
  runId?: string,
  onCompleted?: () => void
): UseSSEResult {
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isCompleted, setIsCompleted] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const isCompletedRef = useRef<boolean>(false);
  const onCompletedRef = useRef(onCompleted);

  useEffect(() => {
    onCompletedRef.current = onCompleted;
  }, [onCompleted]);

  useEffect(() => {
    // If no active run or project, clean up and exit
    if (!projectId || !runId) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      setIsConnected(false);
      return;
    }

    // Reset state for new run
    setEvents([]);
    setIsCompleted(false);
    isCompletedRef.current = false;
    setError(null);

    const url = `/projects/${encodeURIComponent(projectId)}/events?run_id=${encodeURIComponent(runId)}`;
    const es = new EventSource(url);
    eventSourceRef.current = es;
    setIsConnected(true);

    es.onopen = () => {
      setIsConnected(true);
      setError(null);
    };

    es.onmessage = (event) => {
      try {
        if (!event.data || event.data.trim() === "") return;
        const parsed: PipelineEvent = JSON.parse(event.data);

        setEvents((prev) => {
          if (prev.some((e) => e.id === parsed.id)) {
            return prev;
          }
          return [...prev, parsed];
        });

        const status = parsed.data?.status;
        const isFinished =
          parsed.event_type === "WORKFLOW_COMPLETED" ||
          status === "SUCCESS" ||
          status === "FAILED" ||
          status === "NEEDS_INPUT";

        if (isFinished) {
          isCompletedRef.current = true;
          setIsCompleted(true);
          if (status === "FAILED" && parsed.data?.error) {
            setError(parsed.data.error);
          }
          es.close();
          eventSourceRef.current = null;
          setIsConnected(false);
          onCompletedRef.current?.();
        }
      } catch {
        // Safe skip on heartbeat or non-json message
      }
    };

    es.onerror = () => {
      setIsConnected(false);
      es.close();
      eventSourceRef.current = null;
      if (!isCompletedRef.current) {
        setError("Event stream disconnected before run completed.");
      }
    };

    return () => {
      es.close();
      eventSourceRef.current = null;
      setIsConnected(false);
    };
  }, [projectId, runId]);

  const clearEvents = () => setEvents([]);

  return { events, isConnected, isCompleted, error, clearEvents };
}
