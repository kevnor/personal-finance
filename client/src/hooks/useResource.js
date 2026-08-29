import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../lib/api.js";

/**
 * Load something from the API and keep it fresh.
 *
 * Returns { data, error, loading, reload }. Three states rather than two,
 * because "no data yet" and "no data, and here is why" need different
 * screens — rendering an empty list for a failed request tells the user
 * their week was free.
 *
 * `onUnauthorized` is how a session that expired mid-use becomes the login
 * screen instead of an error banner. It is handled here rather than in each
 * caller so no caller can forget.
 */
export function useResource(load, deps = [], { onUnauthorized } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const [nonce, setNonce] = useState(0);
  // Guards against a resolved request writing state after the component has
  // gone, and against an earlier request overwriting a later one's result.
  const current = useRef(0);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    const generation = ++current.current;
    let cancelled = false;
    setState((previous) => ({ ...previous, loading: true, error: null }));

    load()
      .then((data) => {
        if (cancelled || generation !== current.current) return;
        setState({ data, error: null, loading: false });
      })
      .catch((error) => {
        if (cancelled || generation !== current.current) return;
        if (error instanceof ApiError && error.isUnauthorized && onUnauthorized) {
          onUnauthorized();
          return;
        }
        setState({ data: null, error, loading: false });
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  return { ...state, reload };
}

/**
 * Run a write and track whether it is in flight and whether it failed.
 *
 * Writes need this separately from reads: the button must disable while the
 * request is out, or a double tap sends two. Ingest is idempotent but hand
 * entry is not — two taps on "Lagre" would be two transactions.
 */
export function useAction({ onUnauthorized } = {}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);

  const run = useCallback(
    async (fn) => {
      setPending(true);
      setError(null);
      try {
        return await fn();
      } catch (caught) {
        if (caught instanceof ApiError && caught.isUnauthorized && onUnauthorized) {
          onUnauthorized();
          return undefined;
        }
        setError(caught);
        return undefined;
      } finally {
        setPending(false);
      }
    },
    [onUnauthorized],
  );

  return { run, pending, error, clearError: () => setError(null) };
}
