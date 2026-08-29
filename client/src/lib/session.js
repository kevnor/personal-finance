// A local note of whether this browser was signed in last time it asked.
//
// Why this exists: the app gates on `/api/auth/status`, and the service
// worker deliberately never caches that — a cached `authenticated: true`
// would show the app to someone whose session the server has already stopped
// accepting. But that leaves the offline promise unfulfillable: with no
// network the status request fails, the gate cannot resolve, and the user
// gets an error instead of the number the spec says they should see in a
// shop with poor signal.
//
// So: when the request cannot be made at all, fall back to what this browser
// was told the last time it could ask.
//
// This is not an authentication decision and cannot be used as one. It only
// unlocks data already sitting in this browser's own cache, put there by an
// authenticated session on this device — anyone who could read the screen
// this way could equally read the same cache in devtools. Every request the
// app then makes still goes to the server, and a session the server no
// longer accepts comes back 401, which clears this flag and returns to the
// login screen.

const KEY = "pf.signed-in";

// Storage can be unavailable (private mode, disabled site data) and throws
// rather than returning null. The app must work without it — it simply loses
// the offline fallback.
function storage() {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function rememberSignedIn(signedIn) {
  try {
    if (signedIn) storage()?.setItem(KEY, "1");
    else storage()?.removeItem(KEY);
  } catch {
    /* not fatal: the offline fallback is an enhancement */
  }
}

export function wasSignedIn() {
  try {
    return storage()?.getItem(KEY) === "1";
  } catch {
    return false;
  }
}
