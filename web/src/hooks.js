import { useEffect, useRef, useState } from "react";

// A value that only updates after the user stops typing for `ms`.
export function useDebounced(value, ms = 400) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

// State that is saved in this browser (localStorage) and restored on the next visit.
export function useStoredState(key, initial) {
  const [v, setV] = useState(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw === null ? initial : JSON.parse(raw);
    } catch {
      return initial;
    }
  });
  useEffect(() => {
    try {
      if (v === undefined) localStorage.removeItem(key);
      else localStorage.setItem(key, JSON.stringify(v));
    } catch {
      /* private mode or storage full: keep working without saving */
    }
  }, [key, v]);
  return [v, setV];
}

/**
 * Paged feed: fetches page 1 whenever `params` change, then "load more" appends.
 * Stale answers (from an older filter) are ignored.
 */
export function useFeed(fetcher, params, enabled = true, pageSize = 30) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(null);
  const [newCount, setNewCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const reqId = useRef(0);
  const key = JSON.stringify(params);

  const load = async (offset) => {
    const id = ++reqId.current;
    setLoading(true);
    setError(null);
    try {
      const page = await fetcher({ ...params, limit: pageSize, offset });
      if (id !== reqId.current) return;
      setItems((prev) => (offset === 0 ? page.items : [...prev, ...page.items]));
      setTotal(page.total);
      if (offset === 0) setNewCount(page.new_count || 0);
    } catch (e) {
      if (id === reqId.current) setError(e.message);
    } finally {
      if (id === reqId.current) setLoading(false);
    }
  };

  useEffect(() => {
    if (!enabled) return;
    setItems([]);
    setTotal(null);
    setNewCount(0);
    load(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled]);

  return {
    items,
    total,
    newCount,
    loading,
    error,
    hasMore: total !== null && items.length < total,
    loadMore: () => load(items.length),
    retry: () => load(0),
  };
}
