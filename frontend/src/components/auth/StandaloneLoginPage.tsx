import { BrandMark } from "@/components/icons";

interface StandaloneLoginPageProps {
  error?: string;
  isSigningIn: boolean;
  onSignIn: () => void;
}

/** Standalone entry point; VOW itself owns credentials, MFA and recovery. */
export function StandaloneLoginPage({
  error,
  isSigningIn,
  onSignIn,
}: StandaloneLoginPageProps) {
  return (
    <main className="grid min-h-full place-items-center bg-base-200 px-6 py-10 text-base-content">
      <section
        aria-labelledby="login-title"
        className="flex w-full max-w-md flex-col items-center gap-6 rounded-box border border-base-300/70 bg-base-100 p-8 text-center shadow-sm"
      >
        <BrandMark className="size-11" />
        <div className="flex flex-col gap-2">
          <h1 id="login-title" className="text-display font-extrabold">
            Sign in to VOW Agent
          </h1>
          <p className="text-body text-base-content/70">
            Use your VOW account to securely access campaign planning.
          </p>
        </div>

        {error && (
          <p
            role="alert"
            className="w-full rounded-field bg-error/10 px-3 py-2 text-note text-error"
          >
            {error}
          </p>
        )}

        <button
          type="button"
          disabled={isSigningIn}
          onClick={onSignIn}
          className="w-full rounded-field bg-primary px-5 py-3 text-control font-semibold text-primary-content hover:bg-primary/90 disabled:cursor-wait disabled:opacity-60"
        >
          {isSigningIn ? "Redirecting to VOW…" : "Sign in with VOW"}
        </button>

        <p className="text-note text-base-content/60">
          You’ll be redirected to VOW to complete sign-in.
        </p>
      </section>
    </main>
  );
}
