import { ChatInput } from "@/components/chat/ChatInput";
import { MessageList } from "@/components/chat/MessageList";
import { WorkspaceHeader } from "@/components/layout";
import type { ElicitationSubmission } from "@/hooks/use-chat";
import type { DraftSelection } from "@/lib/chat";
import { cn } from "@/lib/utils";
import type { ChatMessage, OptionsBlock } from "@/types/chat";
import type { StrategyPlan } from "@/types/strategy";

const COPY = {
  disclaimer: "VOW Agent can make mistakes. Review important campaign details.",
  answerPlaceholder: "Answer in your own words…",
} as const;

interface ChatWorkspaceProps {
  plan: StrategyPlan;
  messages: ChatMessage[];
  isSending: boolean;
  error: string | null;
  /** The one question the user may answer, or null. */
  activeElicitation: OptionsBlock | null;
  submissions: Record<string, ElicitationSubmission>;
  onSend: (value: string) => void;
  onAnswer: (block: OptionsBlock, draft: DraftSelection) => void;
  className?: string;
}

/**
 * The centre console once a conversation exists: a fixed title bar, the one
 * scroll region on this side of the workspace, and a composer docked beneath
 * it. The transcript's reading measure and the dock's width are independent
 * tokens — the design sets the dock slightly wider than the copy it carries.
 */
export function ChatWorkspace({
  plan,
  messages,
  isSending,
  error,
  activeElicitation,
  submissions,
  onSend,
  onAnswer,
  className,
}: ChatWorkspaceProps) {
  // While a question invites a typed answer, the composer *is* the "something
  // else" field — the design gives the card no other affordance for it. Routing
  // it through `onAnswer` keeps the text tied to its elicitation on the wire
  // rather than arriving as an unrelated turn the server has to guess about.
  const answerable = activeElicitation?.allowCustom ? activeElicitation : null;
  const isConcluded = plan.status === "concluded" || messages.some((m) => m.stage === "concluded");
  const submit = (value: string) =>
    answerable
      ? onAnswer(answerable, { optionIds: [], customText: value })
      : onSend(value);

  return (
    <div className={cn("flex min-w-0 flex-1 flex-col", className)}>
      <WorkspaceHeader name={plan.name} status={plan.status} />

      <div className="flex min-h-0 flex-1 flex-col items-center overflow-y-auto px-8">
        <MessageList
          messages={messages}
          isSending={isSending}
          activeElicitationId={activeElicitation?.id ?? null}
          submissions={submissions}
          onAnswer={onAnswer}
        />
      </div>

      {/* The dock is wider than the transcript by exactly its own horizontal
          padding, so centring both lands their content on the same column. */}
      <div className="mx-auto flex w-full max-w-dock flex-none flex-col gap-2 px-8 pt-3 pb-5">
        {error && (
          <div role="alert" className="alert alert-error alert-soft text-note">
            {error}
          </div>
        )}
        <ChatInput
          onSend={submit}
          disabled={isSending || isConcluded}
          placeholder={
            isConcluded
              ? "Conversation concluded. Start a new session to plan another campaign."
              : answerable
                ? COPY.answerPlaceholder
                : undefined
          }
        />
        <p className="text-center text-note text-base-content/50">
          {COPY.disclaimer}
        </p>
      </div>
    </div>
  );
}
