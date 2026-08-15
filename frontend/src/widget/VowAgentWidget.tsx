import { useEffect, type ComponentProps } from "react";

import { ChatWorkspace, StartScreen } from "@/components/chat";
import { NavRail } from "@/components/layout";
import { StrategyPanel } from "@/components/strategy";
import { useChat } from "@/hooks/use-chat";
import { AgentClientProvider, type AgentClient } from "@/lib/agent";
import { DRAFT_PLAN } from "@/lib/strategy";
import { cn } from "@/lib/utils";

/**
 * Minimal, self-contained shape mirrored by hand from the host's
 * `VowAgentUser` (VowMade `frontend/src/types.d.ts`). Keep in sync with that
 * declaration — this repo cannot import the host's internal `User` type.
 */
export interface VowAgentUser {
  id: string;
  email: string;
  name?: string;
  surname?: string;
}

export interface VowAgentWidgetProps {
  /** Sizing/placement is the host's call — the widget only fills what it's given. */
  className?: string;
  /** Accepted for host compatibility but not rendered: the start screen has no
   *  title bar. Consumed again when the conversation view lands. */
  title?: string;
  tagline?: string;
  /**
   * daisyUI theme name applied to this subtree. Leave undefined to inherit the
   * host page's theme when embedded.
   */
  theme?: string;
  /**
   * Backend base URL. Injected by the host so one bundle can serve many
   * environments; falls back to VITE_API_BASE_URL.
   */
  apiBaseUrl?: string;
  /** Escape hatch: a host may supply its own transport implementation. */
  agentClient?: AgentClient;
  /** Logged-in host-app user, null/undefined when unauthenticated. Not yet
   *  consumed here — accepted so the host can start passing it ahead of the
   *  chat/session backend contract landing. */
  user?: VowAgentUser | null;
}

/**
 * Owns the conversation so it survives the start-screen → workspace swap, and
 * sits inside `AgentClientProvider` because `useChat` reads the transport from
 * it. The plan is fixture-backed until the agent emits one.
 */
function Workspace() {
  const {
    messages,
    isSending,
    error,
    activeElicitation,
    submissions,
    send,
    answerElicitation,
  } = useChat();
  const onSend = (value: string) => void send(value);
  const onAnswer: ComponentProps<typeof ChatWorkspace>["onAnswer"] = (
    block,
    draft,
  ) => void answerElicitation(block, draft);

  if (messages.length === 0) {
    return <StartScreen isSending={isSending} error={error} onSend={onSend} />;
  }

  return (
    <>
      <ChatWorkspace
        plan={DRAFT_PLAN}
        messages={messages}
        isSending={isSending}
        error={error}
        activeElicitation={activeElicitation}
        submissions={submissions}
        onSend={onSend}
        onAnswer={onAnswer}
      />
      <StrategyPanel plan={DRAFT_PLAN} />
    </>
  );
}

/**
 * Self-contained mount point for the chat experience. This is the surface a
 * host application would consume through Module Federation, so it owns its own
 * chrome and its own transport, and carries no route or page-level assumptions.
 */
export function VowAgentWidget({
  className,
  theme,
  apiBaseUrl,
  agentClient,
  user,
}: VowAgentWidgetProps) {
  // Temporary: confirms the host is actually wiring the user prop through
  // before the chat/session backend contract exists to consume it. Guarded so
  // it never reaches a host's production bundle.
  useEffect(() => {
    if (import.meta.env.DEV) {
      console.log("[vow_agent] received user prop:", user);
    }
  }, [user]);

  return (
    <AgentClientProvider client={agentClient} apiBaseUrl={apiBaseUrl}>
      <section
        data-theme={theme}
        className={cn(
          // `vow-agent-widget` is the hook the embedded stylesheet scopes its
          // resets to (`src/widget/widget.css`). The MF build ships no global
          // preflight and no daisyUI root color, so in a host page this class
          // is the *only* thing applying box-sizing, the border reset and the
          // theme's base colors. Removing it silently unstyles the widget when
          // embedded while leaving the standalone app looking fine.
          "vow-agent-widget",
          // Named so `@sm/vow-agent:` resolves against this subtree rather than
          // whatever container a host happens to mount it in.
          "@container/vow-agent",
          "flex min-h-0 w-full flex-1 bg-base-200 text-base-content",
          className,
        )}
      >
        <NavRail />
        <Workspace />
      </section>
    </AgentClientProvider>
  );
}
