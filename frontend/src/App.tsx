import { useEffect, useMemo, useState } from "react";

import { StandaloneLoginPage } from "@/components/auth/StandaloneLoginPage";
import {
  createOidcUserManager,
  OAuthAccessTokenProvider,
  startOAuthRedirect,
  type AccessTokenProvider,
} from "@/lib/auth";
import { config } from "@/lib/config";
import { VowAgentWidget } from "@/widget";

type AuthenticationState = "loading" | "anonymous" | "authenticated";

function AgentSurface({ accessToken }: { accessToken?: AccessTokenProvider }) {
  return (
    <main className="flex min-h-0 flex-1 flex-col">
      <VowAgentWidget accessToken={accessToken} />
    </main>
  );
}

/**
 * Standalone shell. Page-level concerns (filling the viewport) live here so
 * the widget itself stays embeddable.
 */
function OidcStandaloneApp() {
  const manager = useMemo(() => createOidcUserManager(config.oauth), []);
  const tokenProvider = useMemo(
    () => new OAuthAccessTokenProvider(config.oauth, manager, "redirect"),
    [manager],
  );
  const [authentication, setAuthentication] =
    useState<AuthenticationState>("loading");
  const [signInError, setSignInError] = useState<string>();
  const [isSigningIn, setIsSigningIn] = useState(false);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const user = await manager.getUser();
        if (!active) return;
        if (user && !user.expired) {
          setAuthentication("authenticated");
          return;
        }

        if (user?.refresh_token) {
          try {
            const refreshed = await manager.signinSilent({
              resource: config.oauth.resource,
            });
            if (active && refreshed && !refreshed.expired) {
              setAuthentication("authenticated");
              return;
            }
          } catch {
            await manager.removeUser();
          }
        }

        if (active) setAuthentication("anonymous");
      } catch {
        if (!active) return;
        setAuthentication("anonymous");
        setSignInError(
          "Your previous sign-in could not be restored. Please sign in again.",
        );
      }
    })();
    return () => {
      active = false;
    };
  }, [manager]);

  const signIn = async () => {
    setIsSigningIn(true);
    setSignInError(undefined);
    try {
      await startOAuthRedirect(
        config.oauth,
        manager,
        `${window.location.pathname}${window.location.search}${window.location.hash}`,
      );
    } catch {
      setIsSigningIn(false);
      setSignInError("VOW sign-in could not be started. Please try again.");
    }
  };

  if (authentication === "loading") {
    return (
      <main
        aria-label="Restoring VOW sign-in"
        className="grid min-h-full place-items-center bg-base-200 text-body text-base-content/70"
      >
        Restoring your VOW sign-in…
      </main>
    );
  }

  if (authentication === "anonymous") {
    return (
      <StandaloneLoginPage
        error={signInError}
        isSigningIn={isSigningIn}
        onSignIn={() => void signIn()}
      />
    );
  }

  return <AgentSurface accessToken={tokenProvider.getAccessToken} />;
}

export default function App() {
  if (config.authMode === "local") {
    return <AgentSurface />;
  }
  return <OidcStandaloneApp />;
}
