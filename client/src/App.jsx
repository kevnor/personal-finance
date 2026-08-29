import { useCallback, useState } from "react";
import BottomNav from "./components/BottomNav.jsx";
import AddSheet from "./components/AddSheet.jsx";
import { ErrorState, Loading } from "./components/States.jsx";
import { AppDataProvider, buildAppData } from "./context/AppData.jsx";
import { useResource } from "./hooks/useResource.js";
import { api } from "./lib/api.js";
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

  const signedIn = session ?? auth.data?.authenticated ?? false;
  const signOut = useCallback(() => setSession(false), []);

  if (auth.loading && !auth.data) return <Shell><Loading /></Shell>;
  if (auth.error) return <Shell><ErrorState error={auth.error} onRetry={auth.reload} /></Shell>;

  if (!signedIn) {
    return (
      <Shell>
        <Login
          configured={auth.data?.configured ?? false}
          onSignedIn={() => {
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
