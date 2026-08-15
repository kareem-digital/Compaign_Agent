import { useEffect, useRef, useState } from "react";

import { Paperclip, Send } from "@/components/icons";
import { chatLimits } from "@/lib/config";
import { cn } from "@/lib/utils";

/* The one declared place for the composer's height cap. Measured growth is the
 * sanctioned `style` exception, so the ceiling lives here rather than being
 * duplicated as a `max-h-*` class that would then win silently. */
const MAX_HEIGHT_PX = 180;

const COPY = {
  label: "Message VOW Agent",
  placeholder: "Describe the campaign you want to plan…",
  attach: "Attach brief",
  formats: "PDF, DOCX, XLSX, CSV or PPTX",
  send: "Send message",
} as const;

interface ChatInputProps {
  onSend: (value: string) => void;
  disabled?: boolean;
  /** Lets the parent prefill the composer, e.g. from a suggested start. */
  value?: string;
  onValueChange?: (value: string) => void;
  /** Overrides the resting prompt, e.g. while a question is open. */
  placeholder?: string;
}

export function ChatInput({
  onSend,
  disabled = false,
  value,
  onValueChange,
  placeholder = COPY.placeholder,
}: ChatInputProps) {
  const [internalValue, setInternalValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const isControlled = value !== undefined;
  const draft = isControlled ? value : internalValue;

  const setDraft = (next: string) => {
    if (!isControlled) setInternalValue(next);
    onValueChange?.(next);
  };

  // Grow with content up to the cap, then scroll.
  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, MAX_HEIGHT_PX)}px`;
  }, [draft]);

  const canSend = draft.trim().length > 0 && !disabled;

  const submit = () => {
    if (!canSend) return;
    onSend(draft);
    setDraft("");
    textareaRef.current?.focus();
  };

  const remaining = chatLimits.maxMessageLength - draft.length;
  const showCounter = remaining <= 200;

  return (
    <form
      className="w-full"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <div className="rounded-box border border-base-300 bg-base-100 px-5 pt-5 pb-3.5 shadow-lifted focus-within:border-primary/50">
        <label htmlFor="vow-chat-input" className="sr-only">
          {COPY.label}
        </label>
        <textarea
          id="vow-chat-input"
          ref={textareaRef}
          rows={1}
          value={draft}
          disabled={disabled}
          maxLength={chatLimits.maxMessageLength}
          placeholder={placeholder}
          autoComplete="off"
          spellCheck
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
          className="min-h-12 w-full resize-none overflow-y-auto bg-transparent text-body outline-hidden placeholder:text-base-content/50 disabled:opacity-60"
        />

        <div className="flex items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-2.5">
            {/* Inert until an upload endpoint exists — kept at full strength so
                the resting screen matches the design. */}
            <button
              type="button"
              className="relative flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-2 text-control font-semibold text-primary before:absolute before:inset-x-0 before:-inset-y-2"
            >
              <Paperclip className="size-3.5" />
              {COPY.attach}
            </button>
            {/* The design has no hint row, so the counter borrows the format
                slot — it only ever appears near the cap. */}
            <span
              className={cn(
                "truncate text-note",
                remaining <= 0 ? "text-error" : "text-base-content/50",
              )}
            >
              {showCounter ? `${remaining} characters left` : COPY.formats}
            </span>
          </div>

          <button
            type="submit"
            disabled={!canSend}
            aria-label={COPY.send}
            className="btn btn-square btn-primary relative size-10 rounded-field before:absolute before:-inset-0.5"
          >
            <Send className="size-4" />
          </button>
        </div>
      </div>
    </form>
  );
}
