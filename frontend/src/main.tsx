import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "@/App";
import "@/index.css";
import { completeOAuthPopup, completeOAuthRedirect } from "@/lib/auth";
import { config } from "@/lib/config";

const isOAuthPopupCallback = window.location.pathname.endsWith(
  "/agent/oauth/callback",
);
const isOAuthRedirectCallback = window.location.pathname.endsWith(
  "/agent/oauth/login-callback",
);

if (isOAuthRedirectCallback) {
  document.body.textContent = "Completing secure sign-in…";
  void completeOAuthRedirect(config.oauth)
    .then((returnTo) => window.location.replace(returnTo))
    .catch((error: unknown) => {
      document.body.textContent =
        error instanceof Error ? error.message : "Secure sign-in failed.";
    });
} else if (isOAuthPopupCallback) {
  document.body.textContent = "Completing secure sign-in…";
  void completeOAuthPopup(config.oauth).catch((error: unknown) => {
    document.body.textContent =
      error instanceof Error ? error.message : "Secure sign-in failed.";
  });
} else {
  const container = document.getElementById("root");
  if (!container) {
    throw new Error("Root element #root was not found in index.html.");
  }

  createRoot(container).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
