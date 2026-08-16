import { useEffect, useMemo, type ComponentProps } from "react";

import { ChatWorkspace, StartScreen } from "@/components/chat";
import { NavRail } from "@/components/layout";
import { StrategyPanel } from "@/components/strategy";
import { useChat } from "@/hooks/use-chat";
import { AgentClientProvider, type AgentClient } from "@/lib/agent";
import { DRAFT_PLAN } from "@/lib/strategy";
import { cn } from "@/lib/utils";
import type { StrategyPlan } from "@/types/strategy";

const NOT_STATED = "not stated";

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
 * Derives a live StrategyPlan from the backend's summary_list rows.
 * The panel reads real brand, markets, dates, etc. as the agent collects them —
 * no more static "Mega Toothpaste" placeholder disagreeing with the chat.
 */
function buildLivePlan(
  planRows: Array<{ label: string; value: string; field: string }>,
  stage: string | null | undefined,
): StrategyPlan {
  if (planRows.length === 0) return DRAFT_PLAN;

  const get = (field: string) =>
    planRows.find((r) => r.field === field)?.value ?? null;

  const brand = get("brand");
  const markets = get("markets");
  const flight = get("flight_dates");
  const durations = get("durations");
  const budget = get("market_budgets");
  const goal = get("goal");
  const kpi = get("kpi");
  const bid = get("bid");
  const inventory = get("inventory");
  const audience = get("audience");
  const targeting = get("targeting");

  // Track completion across the 4 M1 stages
  const basicFields = [brand, markets, flight, durations, budget];
  const knownBasics = basicFields.filter(
    (v) => v !== null && v !== NOT_STATED,
  ).length;
  const basicsComplete = knownBasics === basicFields.length;
  const inventoryComplete = Boolean(inventory && inventory !== NOT_STATED);
  const targetingComplete = Boolean(audience && audience !== NOT_STATED);
  const isPlanReady = stage === "plan_ready" || stage === "approved";

  let completion = Math.round((knownBasics / basicFields.length) * 40);
  if (inventoryComplete) completion += 25;
  if (targetingComplete) completion += 25;
  if (isPlanReady) completion = 100;

  const basicProperties = [
    { label: "Brand", value: brand },
    { label: "Markets", value: markets },
    { label: "Flight", value: flight },
    { label: "Creative", value: durations },
    { label: "Budget", value: budget },
  ];

  const goalsProperties = [
    { label: "Goal", value: goal },
    { label: "KPI", value: kpi },
    { label: "Bid", value: bid },
  ];

  const inventoryProperties = [
    { label: "Inventory", value: inventory },
    {
      label: "Tier",
      value: inventory
        ? inventory.includes("Prime Video")
          ? "Amazon-owned"
          : "Pre-curated"
        : null,
    },
  ];

  const targetingProperties = [
    { label: "Audience", value: audience },
    { label: "Geo", value: targeting },
  ];

  return {
    name: brand && brand !== NOT_STATED ? brand : "New strategy",
    status: stage === "approved" ? "approved" : "draft",
    completion,
    stages: [
      {
        id: "basic-details",
        title: "Basic details",
        status: basicsComplete ? "complete" : "in-progress",
        isOpen: !basicsComplete,
        properties: basicProperties,
      },
      {
        id: "goals",
        title: "Goals, KPI & bid",
        status: goal && goal !== NOT_STATED ? "complete" : "next",
        isOpen: false,
        properties: goalsProperties,
      },
      {
        id: "inventory",
        title: "CTV inventory",
        status: inventoryComplete
          ? "complete"
          : basicsComplete
            ? "in-progress"
            : "pending",
        isOpen: basicsComplete && !inventoryComplete,
        properties: inventoryProperties,
      },
      {
        id: "targeting",
        title: "Targeting",
        status: targetingComplete
          ? "complete"
          : inventoryComplete
            ? "in-progress"
            : "optional",
        isOpen: inventoryComplete && !targetingComplete,
        properties: targetingProperties,
      },
    ],
    lockedStages: DRAFT_PLAN.lockedStages,
    forecast: null,
  };
}

/**
 * Owns the conversation so it survives the start-screen → workspace swap, and
 * sits inside `AgentClientProvider` because `useChat` reads the transport from
 * it. The plan updates live from the backend's summary_list blocks.
 */
function Workspace() {
  const {
    messages,
    isSending,
    error,
    stage,
    planRows,
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

  // Build a live plan from backend data; falls back to DRAFT_PLAN until first reply.
  const livePlan = useMemo(
    () => buildLivePlan(planRows, stage),
    [planRows, stage],
  );

  if (messages.length === 0) {
    return <StartScreen isSending={isSending} error={error} onSend={onSend} />;
  }

  return (
    <>
      <ChatWorkspace
        plan={livePlan}
        messages={messages}
        isSending={isSending}
        error={error}
        activeElicitation={activeElicitation}
        submissions={submissions}
        onSend={onSend}
        onAnswer={onAnswer}
      />
      <StrategyPanel plan={livePlan} />
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
