import { useState } from "react";

import { ChatInput } from "@/components/chat/ChatInput";
import {
  BrandMark,
  DollarCircle,
  FileText,
  Info,
  PlayRect,
  Upload,
} from "@/components/icons";
import { cn } from "@/lib/utils";

const COPY = {
  title: "Start planning",
  lede: "Describe your objective or attach a brief. VOW Agent will structure the inputs and show what still needs your review.",
  disclaimer: "VOW Agent can make mistakes. Review important campaign details.",
  suggested: "Suggested starts",
} as const;

/** `label` is the chip's own wording; `prompt` is what it drops in the composer. */
const SUGGESTED_STARTS = [
  {
    label: "Upload campaign brief",
    prompt: "I have a campaign brief to work from — help me structure it.",
    Icon: Upload,
  },
  {
    label: "Plan a Prime Video campaign",
    prompt: "Plan a Prime Video CTV campaign for an upcoming product launch.",
    Icon: PlayRect,
  },
  {
    label: "Start with a fixed budget",
    prompt: "I have a fixed budget to spend — help me plan the flight around it.",
    Icon: DollarCircle,
  },
  {
    label: "Structure an incomplete brief",
    prompt: "My brief is missing details. Ask me what you need to complete it.",
    Icon: FileText,
  },
] as const;

interface StartScreenProps {
  isSending: boolean;
  error: string | null;
  onSend: (value: string) => void;
  className?: string;
}

/**
 * The entry screen: brand mark, one elevated composer and a set of suggested
 * starts, centred in the space the rail leaves. Conversation state is owned
 * above this — the first send swaps this surface for the workspace, so it must
 * survive the swap.
 */
export function StartScreen({
  isSending,
  error,
  onSend,
  className,
}: StartScreenProps) {
  const [draft, setDraft] = useState("");

  const handleSend = (value: string) => {
    setDraft("");
    onSend(value);
  };

  return (
    <div
      className={cn(
        "grid min-w-0 flex-1 place-items-center px-10 pb-8",
        className,
      )}
    >
      <div className="flex w-full max-w-composer flex-col gap-6">
        <div className="flex flex-col items-center gap-3 text-center">
          <BrandMark className="size-9" />
          <h1 className="text-display font-extrabold text-base-content">
            {COPY.title}
          </h1>
          <p className="max-w-lede text-pretty text-body text-base-content/70">
            {COPY.lede}
          </p>
        </div>

        <div className="flex flex-col gap-2.5">
          {error && (
            <div
              role="alert"
              className="rounded-field bg-error/10 px-3 py-2 text-note text-error"
            >
              {error}
            </div>
          )}
          <ChatInput
            value={draft}
            onValueChange={setDraft}
            onSend={handleSend}
            disabled={isSending}
          />
          <p className="flex items-center justify-center gap-1.5 text-note text-base-content/60">
            <Info className="size-3.5 flex-none" />
            {COPY.disclaimer}
          </p>
        </div>

        <div className="flex flex-col gap-3">
          <h2 className="text-xs font-bold uppercase tracking-label text-base-content/60">
            {COPY.suggested}
          </h2>
          <ul className="flex flex-wrap gap-2">
            {SUGGESTED_STARTS.map(({ label, prompt, Icon }) => (
              <li key={label}>
                <button
                  type="button"
                  disabled={isSending}
                  onClick={() => setDraft(prompt)}
                  className="flex items-center gap-2 rounded-full border border-base-300/70 bg-base-100 px-3.5 py-2.5 text-control font-semibold text-primary hover:border-primary/40 disabled:opacity-60"
                >
                  <Icon className="size-3.5 flex-none" />
                  {label}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
