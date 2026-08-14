import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./styles.css";

async function startApplication() {
  const root = document.getElementById("root")!;
  const remoteAppUrl = import.meta.env.VITE_REMOTE_APP_URL?.trim().replace(/\/$/, "");
  if (import.meta.env.MODE === "desktop" && remoteAppUrl) {
    root.innerHTML = '<div class="desktop-bootstrap">正在连接最新版本…</div>';
    try {
      await fetch(remoteAppUrl, {
        mode: "no-cors",
        cache: "no-store",
        signal: AbortSignal.timeout(3_000),
      });
      window.location.replace(remoteAppUrl);
      return;
    } catch {
      root.replaceChildren();
    }
  }

  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

void startApplication();

if (import.meta.env.PROD && import.meta.env.MODE !== "desktop" && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("/sw.js");
  });
}
