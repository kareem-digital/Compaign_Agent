import { useEffect, useRef } from "react";

import { MessageBubble } from "@/components/chat/MessageBubble";
import { TypingIndicator } from "@/components/chat/TypingIndicator";
import type { ElicitationSubmission } from "@/hooks/use-chat";
import type { DraftSelection } from "@/lib/chat";
import type { ChatMessage, OptionsBlock } from "@/types/chat";

interface MessageListProps {
  messages: ChatMessage[];
  isSending: boolean;
  /** The one question the user may answer, or null. */
  activeElicitationId: string | null;
  submissions: Record<string, ElicitationSubmission>;
  onAnswer: (block: OptionsBlock, draft: DraftSelection) => void;
}

export function MessageList({
  messages,
  isSending,
  activeElicitationId,
  submissions,
  onAnswer,
}: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages, isSending]);

  return (
    <div
      className="flex w-full max-w-transcript flex-col gap-4 py-4"
      role="log"
      aria-live="polite"
      aria-label="Conversation"
    >
      {messages.map((message) => (
        <MessageBubble
          key={message.id}
          message={message}
          messages={messages}
          activeElicitationId={activeElicitationId}
          submissions={submissions}
          onAnswer={onAnswer}
        />
      ))}
      {isSending && <TypingIndicator />}
      <div ref={endRef} />
    </div>
  );
}
