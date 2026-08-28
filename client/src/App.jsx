import { useState } from "react";
import BottomNav from "./components/BottomNav.jsx";
import AddSheet from "./components/AddSheet.jsx";
import Home from "./pages/Home.jsx";
import History from "./pages/History.jsx";
import Stats from "./pages/Stats.jsx";
import Settings from "./pages/Settings.jsx";
import Review from "./pages/Review.jsx";
import Owed from "./pages/Owed.jsx";
import { REVIEW_QUEUE, REIMBURSEMENTS } from "./lib/mockData.js";

const NAV_TABS = new Set(["home", "history", "stats", "settings"]);

export default function App() {
  const [tab, setTab] = useState("home");
  const [addOpen, setAddOpen] = useState(false);
  const [addedRows, setAddedRows] = useState([]);
  const [reviewQueue, setReviewQueue] = useState(REVIEW_QUEUE);
  const [reviewTotal] = useState(REVIEW_QUEUE.length);
  const [reimbursements, setReimbursements] = useState(REIMBURSEMENTS);

  const goHome = () => setTab("home");
  const resolveReview = (id, category) =>
    setReviewQueue((q) => q.filter((row) => row.id !== id));
  const settleReimbursement = (id) =>
    setReimbursements((items) => items.filter((item) => item.id !== id));

  const owedTotal = reimbursements.reduce((sum, item) => sum + item.amount, 0);

  let page;
  if (tab === "review") {
    page = <Review queue={reviewQueue} total={reviewTotal} onResolve={resolveReview} onBack={goHome} />;
  } else if (tab === "owed") {
    page = <Owed items={reimbursements} onSettle={settleReimbursement} onBack={goHome} />;
  } else if (tab === "history") {
    page = <History />;
  } else if (tab === "stats") {
    page = <Stats />;
  } else if (tab === "settings") {
    page = <Settings />;
  } else {
    page = (
      <Home
        extraRows={addedRows}
        reviewCount={reviewQueue.length}
        owed={owedTotal}
        onReviewClick={() => setTab("review")}
        onOwedClick={() => setTab("owed")}
      />
    );
  }

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
        {page}
      </div>

      <AddSheet
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onSave={({ amount, merchant, category }) =>
          setAddedRows((rows) => [{ name: merchant, category, amount, dot: "var(--accent-300)" }, ...rows])
        }
      />

      <BottomNav active={NAV_TABS.has(tab) ? tab : null} onSelect={setTab} onAdd={() => setAddOpen(true)} />
    </div>
  );
}
