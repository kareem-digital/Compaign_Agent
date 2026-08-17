import { OptionsBlockCard } from "@/components/chat/OptionsBlockCard";
import { BrandMark } from "@/components/icons";
import type { ElicitationSubmission } from "@/hooks/use-chat";
import { resolveAnswerLabels, type DraftSelection } from "@/lib/chat";
import type { ChatMessage, OptionsBlock } from "@/types/chat";

const COPY = { recorded: "Selection recorded" } as const;

interface MessageBubbleProps {
  message: ChatMessage;
  /** The whole transcript, for resolving an answer's option ids to labels. */
  messages: ChatMessage[];
  /** The one question the user may answer, or null. */
  activeElicitationId: string | null;
  submissions: Record<string, ElicitationSubmission>;
  onAnswer: (block: OptionsBlock, draft: DraftSelection) => void;
}

/**
 * Two asymmetric turn treatments, per the design: the user speaks in a tinted
 * bubble at the inline end, the agent speaks as flowed copy behind its mark.
 * Neither carries a timestamp — the transcript is a conversation, not a log.
 *
 * A turn is a list of blocks, so an agent reply can be prose, a question the
 * user taps, or both.
 */
export function MessageBubble({
  message,
  messages,
  activeElicitationId,
  submissions,
  onAnswer,
}: MessageBubbleProps) {
  if (message.role === "user") {
    // The user's turn is text or a recorded answer, never an options card —
    // and an answer renders from labels, so the model-facing value, which the
    // domain model doesn't even carry, cannot surface here.
    const text = message.content
      .map((block) => {
        if (block.type === "text") return block.text;
        if (block.type !== "options_answer") return "";
        const { labels, customText } = resolveAnswerLabels(messages, block);
        const parts = [...labels, ...(customText ? [customText] : [])];
        return parts.length ? parts.join(", ") : COPY.recorded;
      })
      .filter(Boolean)
      .join("\n");

    return (
      <div className="flex justify-end">
        {/* Plain text only — never dangerouslySetInnerHTML. */}
        <div className="max-w-4/5 whitespace-pre-wrap break-words rounded-box rounded-ee-sm bg-primary/10 px-4 py-3 text-body text-base-content">
          {text}
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3">
      <BrandMark className="mt-0.5 size-6.5 flex-none" />
      <div className="flex min-w-0 flex-1 flex-col gap-2.5 text-base-content">
        {message.content.map((block, index) => {
          const key = `${message.id}-${index}`;

          if (block.type === "options") {
            return (
              <OptionsBlockCard
                key={key}
                block={block}
                interactive={block.id === activeElicitationId}
                submission={submissions[block.id]}
                onAnswer={onAnswer}
              />
            );
          }

          return (
            <p key={key} className="whitespace-pre-wrap break-words text-body">
              {block.type === "text" ? block.text : COPY.recorded}
            </p>
          );
        })}
      </div>
    </div>
  );
}
