"use client";

import { useCallback, useEffect, useRef } from "react";
import { useAuthStore } from "@/lib/store";

type EventHandler = (data: any) => void;

const handlers = new Map<string, Set<EventHandler>>();
let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
const MAX_RECONNECT_ATTEMPTS = 5;
let reconnectAttempts = 0;

export function subscribe(event: string, handler: EventHandler) {
  if (!handlers.has(event)) handlers.set(event, new Set());
  handlers.get(event)!.add(handler);
  return () => handlers.get(event)?.delete(handler);
}

export function useSSE() {
  const token = useAuthStore((s) => s.token);
  const eventSourceRef = useRef<EventSource | null>(null);
  const isConnectingRef = useRef(false);

  const connectSSE = useCallback(() => {
    if (!token || isConnectingRef.current) return;
    isConnectingRef.current = true;

    try {
      const url = `/api/v1/events?token=${encodeURIComponent(token)}`;
      const es = new EventSource(url);
      eventSourceRef.current = es;

      es.onopen = () => {
        reconnectAttempts = 0;
        isConnectingRef.current = false;
      };

      const handleEvent = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          const type = event.type;
          const typeHandlers = handlers.get(type);
          if (typeHandlers) typeHandlers.forEach((fn) => fn(data));
          const wildHandlers = handlers.get("*");
          if (wildHandlers) wildHandlers.forEach((fn) => fn(data));
        } catch {
          // ignore parse errors
        }
      };

      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          const eventHandlers = handlers.get(data.type || "*");
          if (eventHandlers) eventHandlers.forEach((fn) => fn(data));
        } catch {
          // ignore
        }
      };

      es.addEventListener("job_stage_changed", handleEvent);
      es.addEventListener("job_completed", handleEvent);
      es.addEventListener("job_failed", handleEvent);
      es.addEventListener("batch_progress", handleEvent);
      es.addEventListener("acquisition_alert", handleEvent);
      es.addEventListener("system_alert", handleEvent);
      es.addEventListener("notification", handleEvent);

      es.onerror = () => {
        es.close();
        eventSourceRef.current = null;
        isConnectingRef.current = false;

        if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttempts++;
          const backoffMs = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
          reconnectTimeout = setTimeout(() => {
            connectSSE();
          }, backoffMs);
        }
      };
    } catch {
      isConnectingRef.current = false;
    }
  }, [token]);

  useEffect(() => {
    connectSSE();
    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      isConnectingRef.current = false;
    };
  }, [connectSSE]);
}

export function useSSEEvent(event: string, handler: EventHandler) {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    const wrapped = (data: any) => handlerRef.current(data);
    const unsub = subscribe(event, wrapped);
    return () => { unsub(); };
  }, [event]);
}
