import { useCallback, useEffect, useState } from "react";
import { api } from "../services/api";
import type { ApiContext } from "../types/api";

const POLL_INTERVAL_MS = 800;

export function useDashboard() {
  const [data, setData] = useState<ApiContext | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const refresh = useCallback(async (initial = false) => {
    if (initial) setRefreshing(true);
    try {
      const fresh = await api.getDashboard();
      setData(fresh);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Backend connection failed.");
    } finally {
      if (initial) setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    let stopped = false;
    let timer: number | undefined;

    const poll = async () => {
      try {
        const snapshot = await api.getState();
        if (!stopped) {
          setData(current => current ? { ...current, snapshot } : current);
          setError(null);
        }
      } catch (cause) {
        if (!stopped) setError(cause instanceof Error ? cause.message : "Backend connection failed.");
      } finally {
        if (!stopped) timer = window.setTimeout(poll, POLL_INTERVAL_MS);
      }
    };

    void refresh(true).then(() => {
      if (!stopped) timer = window.setTimeout(poll, POLL_INTERVAL_MS);
    });
    return () => {
      stopped = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [refresh]);

  return { data, error, refreshing, refresh };
}
