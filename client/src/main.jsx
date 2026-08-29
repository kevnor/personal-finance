import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import { registerServiceWorker } from "./lib/registerSW.js";
import "./index.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

// After render, not before: the worker is an enhancement and must never sit
// between the user and the first paint.
registerServiceWorker();
