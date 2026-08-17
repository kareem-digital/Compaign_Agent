/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Agent backend base URL, e.g. http://localhost:8001/api/v1. */
  readonly VITE_API_BASE_URL?: string;
  /** Use `local` only with a local backend configured for AUTH_MODE=local. */
  readonly VITE_AUTH_MODE?: "oidc" | "local";
  readonly VITE_VOW_OIDC_AUTHORITY?: string;
  readonly VITE_VOW_OAUTH_CLIENT_ID?: string;
  readonly VITE_VOW_AGENT_RESOURCE?: string;
  readonly VITE_VOW_OAUTH_REDIRECT_URI?: string;
  readonly VITE_VOW_OAUTH_POPUP_REDIRECT_URI?: string;
  readonly VITE_VOW_OAUTH_SCOPE?: string;
  readonly VITE_ADVERTISER_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
