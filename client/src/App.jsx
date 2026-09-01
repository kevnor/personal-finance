import { useCallback, useEffect, useState } from "react";
import BottomNav from "./components/BottomNav.jsx";
import AddSheet from "./components/AddSheet.jsx";
import { ErrorState, Loading, OfflineBar } from "./components/States.jsx";
import { AppDataProvider, buildAppData } from "./context/AppData.jsx";
import { useOnline } from "./hooks/useOnline.js";
import { useResource } from "./hooks/useResource.js";
import { api } from "./lib/api.js";
import { rememberSignedIn, signedInVia, wasSignedIn } from "./lib/session.js";
import Home from "./pages/Home.jsx";
import History from "./pages/History.jsx";
import Login from "./pages/Login.jsx";
import Stats from "./pages/Stats.jsx";
import Settings from "./pages/Settings.jsx";
import Review from "./pages/Review.jsx";
import Owed from "./pages/Owed.jsx";

const NAV_TABS = new Set(["home", "history", "stats", "settings"]);

export default function App() {
  // Bumped whenever a write lands, so every screen reloads from the server
  // rather than each keeping its own optimistic copy. One user on a fast
  // local network does not need optimistic updates, and a screen showing an
  // edit the server rejected is worse than a screen half a second behind.
  const [revision, setRevision] = useState(0);
  const changed = useCallback(() => setRevision((n) => n + 1), []);

  const [session, setSession] = useState(null);
  const auth = useResource(() => api.auth.status(), [revision]);

  const signOut = useCallback(() => {
    rememberSignedIn(false);
    setSession(false);
  }, []);

  // Record the answer whenever the server gives one, so there is something to
  // fall back on when it cannot be reached.
  useEffect(() => {
    if (auth.data) rememberSignedIn(auth.data.authenticated, auth.data.source);
  }, [auth.data]);

  // Why the app came back here, when it came back from Entra. `required`
  // means a silent renewal could not be completed without showing the user
  // something -- their directory session lapsed, or they are no longer
  // assigned -- so it is a prompt rather than an error.
  const notice = new URLSearchParams(window.location.search).get("signin");

  // An Entra session lasts an hour, so it lapses during ordinary use. Rather
  // than dropping the user on a login screen, spend one round trip asking the
  // directory to confirm them without interaction. Only worth attempting when
  // this browser signed in that way to begin with -- after an explicit
  // sign-out the note is cleared, so logging out is not instantly undone.
  //
  // `notice` is the loop guard: arriving back with one means the attempt has
  // already been made and did not succeed, and retrying would spin.
  const renewing =
    auth.data?.authenticated === false &&
    auth.data?.entra_available === true &&
    signedInVia() === "entra" &&
    !notice;

  useEffect(() => {
    if (!renewing) return;
    const here = window.location.pathname + window.location.search;
    window.location.assign(
      `/api/auth/entra/login?silent=true&next=${encodeURIComponent(here)}`,
    );
  }, [renewing]);

  // The server could not be reached at all (status 0, not an HTTP error). The
  // worker never caches auth state -- a cached `authenticated: true` would
  // show the app to someone whose session the server has already stopped
  // accepting -- so there is no answer to fall back to except the local note.
  // See lib/session.js for why trusting it here is not an authentication
  // decision: it only unlocks this browser's own cache.
  if (auth.error?.status === 0 && wasSignedIn()) {
    return <SignedIn revision={revision} onChanged={changed} onSignedOut={signOut} />;
  }

  const signedIn = session ?? auth.data?.authenticated ?? false;

  // Mid-renewal the browser is already navigating away; a login screen drawn
  // for the intervening frame would flash and then vanish.
  if (renewing || (auth.loading && !auth.data)) return <Shell><Loading /></Shell>;
  if (auth.error) return <Shell><ErrorState error={auth.error} onRetry={auth.reload} /></Shell>;

  if (!signedIn) {
    return (
      <Shell>
        <Login
          configured={auth.data?.configured ?? false}
          entraAvailable={auth.data?.entra_available ?? false}
          notice={notice}
          onSignedIn={() => {
            rememberSignedIn(true, "passcode");
            setSession(true);
            changed();
          }}
        />
      </Shell>
    );
  }

  return <SignedIn revision={revision} onChanged={changed} onSignedOut={signOut} />;
}

/**
 * The app proper: everything below here can assume a session.
 *
 * Split from `App` so the reference data load happens once, after sign-in,
 * rather than on every render of the gate — and so a 401 from any screen
 * unmounts the lot and returns to the login form.
 */
function SignedIn({ revision, onChanged, onSignedOut }) {
  const [tab, setTab] = useState("home");
  const [addOpen, setAddOpen] = useState(false);
  const online = useOnline();

  const reference = useResource(
    () => Promise.all([api.categories.list(), api.accounts.list()]),
    [revision],
    { onUnauthorized: onSignedOut },
  );

  if (reference.loading && !reference.data) return <Shell><Loading /></Shell>;
  if (reference.error) {
    return (
      <Shell>
        <ErrorState error={reference.error} onRetry={reference.reload} />
      </Shell>
    );
  }

  const [categories, accounts] = reference.data;
  const appData = buildAppData(categories, accounts);
  const goHome = () => setTab("home");
  const shared = { revision, onChanged, onUnauthorized: onSignedOut };

  let page;
  if (tab === "review") {
    page = <Review {...shared} onBack={goHome} />;
  } else if (tab === "owed") {
    page = <Owed {...shared} onBack={goHome} />;
  } else if (tab === "history") {
    page = <History {...shared} />;
  } else if (tab === "stats") {
    page = <Stats {...shared} />;
  } else if (tab === "settings") {
    page = <Settings {...shared} onSignedOut={onSignedOut} />;
  } else {
    page = (
      <Home
        {...shared}
        onReviewClick={() => setTab("review")}
        onOwedClick={() => setTab("owed")}
        onHistoryClick={() => setTab("history")}
      />
    );
  }

  return (
    <AppDataProvider value={appData}>
      <Shell
        chrome={
          <>
            <AddSheet
              open={addOpen}
              onClose={() => setAddOpen(false)}
              onSaved={onChanged}
              onUnauthorized={onSignedOut}
            />
            <BottomNav
              active={NAV_TABS.has(tab) ? tab : null}
              onSelect={setTab}
              onAdd={() => setAddOpen(true)}
            />
          </>
        }
      >
        {!online && <div style={{ marginBottom: 14 }}><OfflineBar /></div>}
        {page}
      </Shell>
    </AppDataProvider>
  );
}

/**
 * The phone-shaped frame.
 *
 * `chrome` is rendered as a sibling of the scrolling area, not inside it:
 * the bottom nav and the add sheet are positioned against `.app-shell`, and
 * putting them in the scroll container would carry them off-screen with the
 * content.
 */
function Shell({ children, chrome }) {
  return (
    <div className="app-shell">
      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflow: "auto",
          padding: "24px 20px 100px",
          boxSizing: "border-box",
        }}
      >
        {children}
      </div>
      {chrome}
    </div>
  );
}
