import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * useAgentSession(sessionId)
 *
 * Real WebSocket client hook matching ML Agent backend schema.
 * - Auto-reconnects on drop (3s backoff)
 * - Handles multipart file uploads to /upload
 * - Emits real user_messages
 * - Collects real backend events:
 *     node_start, node_end, thinking, tool_call, tool_result, eda_report,
 *     code_block, execution_result, selector_verdict, human_input_request,
 *     error, assistant_message, chart
 */
export function useAgentSession(sessionId) {
  const [messages, setMessages] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [activeNode, setActiveNode] = useState(null); // 'data_explorer' | 'planner' | 'coder' | 'execute' | 'selector'
  const [pendingHumanQuestion, setPendingHumanQuestion] = useState(null);
  const [experiments, setExperiments] = useState([]);

  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const isMountedRef = useRef(true);

  const handleIncomingEvent = useCallback((event) => {
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const eventId = `ev-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;

    switch (event.type) {
      case 'user_message':
        setMessages((prev) => [
          ...prev,
          {
            id: eventId,
            type: 'user_message',
            sender: 'user',
            content: event.content,
            attachments: event.attachments || [],
            attachmentDetails: event.attachmentDetails || [],
            timestamp,
          },
        ]);
        break;

      case 'node_start':
        setActiveNode(event.node);
        setIsRunning(true);
        setMessages((prev) => [
          ...prev,
          {
            id: eventId,
            type: 'node_start',
            node: event.node,
            timestamp,
          },
        ]);
        break;

      case 'node_end':
        setMessages((prev) => [
          ...prev,
          {
            id: eventId,
            type: 'node_end',
            node: event.node,
            timestamp,
          },
        ]);
        break;

      case 'thinking':
        setMessages((prev) => [
          ...prev,
          {
            id: eventId,
            type: 'thinking',
            node: event.node,
            summary: event.summary || 'Reasoning process',
            trace: event.trace || event.content || [],
            duration: event.duration || (event.node ? `${event.node} reasoning` : 'Reasoning trace'),
            timestamp,
          },
        ]);
        break;

      case 'tool_call':
      case 'tool_result':
        setMessages((prev) => [
          ...prev,
          {
            id: eventId,
            type: event.type,
            node: event.node,
            tool: event.tool,
            input: event.input,
            output: event.output,
            timestamp,
          },
        ]);
        break;

      case 'eda_report':
        setMessages((prev) => [
          ...prev,
          {
            id: eventId,
            type: 'eda_report',
            summary: event.summary,
            contentMarkdown: event.content_markdown,
            charts: event.charts || {},
            timestamp,
          },
        ]);
        break;

      case 'code_block':
        setMessages((prev) => [
          ...prev,
          {
            id: eventId,
            type: 'code_block',
            language: event.language || 'python',
            content: event.content,
            node: event.node,
            timestamp,
          },
        ]);
        break;

      case 'execution_result':
        setMessages((prev) => [
          ...prev,
          {
            id: eventId,
            type: 'execution_result',
            experiment_id: event.experiment_id,
            cv_mean: event.cv_mean,
            cv_std: event.cv_std,
            status: event.status,
            stdout_tail: event.stdout_tail,
            stderr_tail: event.stderr_tail,
            error: event.error,
            timestamp,
          },
        ]);
        setExperiments((prev) => [
          ...prev,
          {
            experiment_id: event.experiment_id,
            cv_mean: event.cv_mean,
            cv_std: event.cv_std,
            status: event.status,
            timestamp,
          },
        ]);
        break;

      case 'chart':
        setMessages((prev) => [
          ...prev,
          {
            id: eventId,
            type: 'chart',
            node: event.node,
            experiment_id: event.experiment_id,
            title: event.title || 'Visualization',
            filename: event.filename,
            image_base64: event.image_base64,
            timestamp,
          },
        ]);
        break;

      case 'selector_verdict':
        setMessages((prev) => [
          ...prev,
          {
            id: eventId,
            type: 'selector_verdict',
            decision: event.decision,
            detail: event.detail,
            methodology_note: event.methodology_note,
            timestamp,
          },
        ]);
        if (event.decision === 'converge') {
          setIsRunning(false);
          setActiveNode(null);
        }
        break;

      case 'human_input_request':
        setPendingHumanQuestion({
          question: event.question,
          context: event.context,
        });
        setMessages((prev) => [
          ...prev,
          {
            id: eventId,
            type: 'human_input_request',
            question: event.question,
            context: event.context,
            timestamp,
          },
        ]);
        break;

      case 'assistant_message':
        setMessages((prev) => [
          ...prev,
          {
            id: eventId,
            type: 'assistant_message',
            sender: 'assistant',
            content: event.content,
            timestamp,
          },
        ]);
        break;

      case 'error':
        setMessages((prev) => [
          ...prev,
          {
            id: eventId,
            type: 'error',
            node: event.node,
            message: event.message,
            timestamp,
          },
        ]);
        setIsRunning(false);
        setActiveNode(null);
        break;

      default:
        break;
    }
  }, []);

  const eventHandlerRef = useRef(handleIncomingEvent);
  useEffect(() => {
    eventHandlerRef.current = handleIncomingEvent;
  }, [handleIncomingEvent]);

  const connectRef = useRef(null);

  const connect = useCallback(() => {
    if (!sessionId) return;
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const url = `${protocol}//${host}/ws/session/${sessionId}`;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!isMountedRef.current) return;
        setIsConnected(true);
      };

      ws.onclose = () => {
        if (!isMountedRef.current) return;
        setIsConnected(false);
        // Auto-reconnect after 3s
        reconnectTimerRef.current = setTimeout(() => {
          if (isMountedRef.current && connectRef.current) {
            connectRef.current();
          }
        }, 3000);
      };

      ws.onerror = (err) => {
        console.warn('[WS] Error:', err);
      };

      ws.onmessage = (event) => {
        if (!isMountedRef.current) return;
        try {
          const data = JSON.parse(event.data);
          eventHandlerRef.current(data);
        } catch (err) {
          console.error('[WS] Parse error:', err);
        }
      };
    } catch (err) {
      console.error('[WS] Connection failed:', err);
    }
  }, [sessionId]);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    isMountedRef.current = true;
    connect();

    return () => {
      isMountedRef.current = false;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  // Upload file to /upload (multipart)
  const uploadFile = useCallback(async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch('/upload', { method: 'POST', body: formData });
    if (!res.ok) {
      throw new Error(`Upload failed for ${file.name}`);
    }
    const data = await res.json();
    return data; // { handle, filename, size }
  }, []);

  // Send message via WebSocket
  const sendMessage = useCallback(
    ({ content, attachments = [], attachmentDetails = [] }) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        console.warn('[WS] WebSocket is not connected.');
        return false;
      }

      const handles = attachments.map((a) => (typeof a === 'string' ? a : a.handle));

      const payload = {
        type: 'user_message',
        content,
        attachments: handles,
        attachmentDetails,
      };

      wsRef.current.send(JSON.stringify(payload));
      setIsRunning(true);
      setPendingHumanQuestion(null);
      return true;
    },
    []
  );

  const clearMessages = useCallback(() => {
    setMessages([]);
    setExperiments([]);
    setIsRunning(false);
    setActiveNode(null);
    setPendingHumanQuestion(null);
  }, []);

  return {
    messages,
    setMessages,
    isConnected,
    isRunning,
    activeNode,
    pendingHumanQuestion,
    experiments,
    uploadFile,
    sendMessage,
    clearMessages,
  };
}
