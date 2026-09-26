import { useEffect, useState } from 'react';
import { apiGet } from '../api/client';

/** Polls GET /sovereignty/network every `intervalMs` while mounted. */
export default function useNetworkStatus(intervalMs = 2000) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const next = await apiGet('/sovereignty/network');
        if (!cancelled) {
          setData(next);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err.message || 'unavailable');
      }
    };
    tick();
    const timer = setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [intervalMs]);

  return { data, error };
}
