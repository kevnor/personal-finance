import { useEffect, useState } from "react";

/**
 * Whether the browser thinks it has a network.
 *
 * Worth showing because the offline behaviour is deliberately asymmetric:
 * reads fall back to the last cached response, so the app keeps working,
 * while writes fail outright. Without a hint, a user in a shop with no
 * signal sees a normal-looking app that silently refuses to save anything.
 *
 * `navigator.onLine` is a lower bound, not a promise: it reports the link,
 * not whether the server is reachable. False here means definitely offline;
 * true means "there is a network", which is why the API wrapper still has to
 * handle a failed fetch.
 */
export function useOnline() {
  const [online, setOnline] = useState(
    typeof navigator === "undefined" ? true : navigator.onLine,
  );

  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);

  return online;
}
