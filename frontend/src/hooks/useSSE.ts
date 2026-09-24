import { useState, useEffect, useRef } from "react";
import { PipelineEvent } from "../types";

interface UseSSEResult {
  events: PipelineEvent[];
  isConnected: boolean;
  isCompleted: boolean;
  error: string | null;
  clearEvents: () => void;
}

export function useSSE(projectId?: string, runId?: string): UseSSEResult {
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isCompleted, setIsCompleted] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!projectId || !runId) {
      setIsConnected(false);
      return;
    }

    setEvents([]);
    setIsCompleted(false);
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
        const parsed: PipelineEvent = JSON.parse(event.data);
        setEvents((prev) => {
          // Avoid duplicate event IDs
          if (prev.some((e) => e.id === parsed.id)) {
            return prev;
          }
          return [...prev, parsed];
        });

        if (parsed.event_type === "WORKFLOW_COMPLETED") {
          setIsCompleted(true);
          es.close();
          setIsConnected(false);
        }
      } catch (err) {
        // Heartbeat or ping event
      }
    };

    es.onerror = () => {
      setIsConnected(false);
      // If error occurs after some events or completed, close gracefully
      es.close();
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
