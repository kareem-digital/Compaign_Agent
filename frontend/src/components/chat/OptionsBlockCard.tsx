import { useEffect, useId, useState } from "react";

import { Check, ChevronRight, Send } from "@/components/icons";
import type { ElicitationSubmission } from "@/hooks/use-chat";
import type { DraftSelection } from "@/lib/chat";
import { chatLimits } from "@/lib/config";
import { cn } from "@/lib/utils";
import type { OptionChoice, OptionsBlock } from "@/types/chat";

const COPY = {
  singleHint: "Pick one — press 1–9 — then confirm, or answer in your own words",
  multiHint: "Pick any that apply, then confirm",
  customFallback: "Something else…",
  confirm: "Confirm",
  send: "Send answer",
  superseded: "We moved on from this question.",
  expired: "This question is no longer open.",
  stale: "Only the latest question can be answered.",
} as const;

interface OptionsBlockCardProps {
  block: OptionsBlock;
  /** True only for the newest still-pending question. */
  interactive: boolean;
  submission?: ElicitationSubmission;
  onAnswer: (block: OptionsBlock, draft: DraftSelection) => void;
}

/** Why the question can't be answered, when that isn't obvious. */
function hintFor(block: OptionsBlock, interactive: boolean): string | null {
  if (block.status === "superseded") return COPY.superseded;
  if (block.status === "expired") return COPY.expired;
  if (block.status === "pending" && !interactive) return COPY.stale;
  return null;
}

/** A keystroke aimed at a field is never a shortcut. */
function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.isContentEditable ||
    ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)
  );
}

interface OptionRowProps {
  option: OptionChoice;
  index: number;
  select: OptionsBlock["select"];
  isChosen: boolean;
  disabled: boolean;
  onSelect: () => void;
}

/**
 * One tappable row. The leading indicator is the only thing the two selection
 * modes differ on: a checkbox reads "any number of these", a numbered token
 * reads "one of these, and here is its shortcut key".
 */
function OptionRow({
  option,
  index,
  select,
  isChosen,
  disabled,
  onSelect,
}: OptionRowProps) {
  const className = cn(
    "flex w-full items-center gap-3 rounded-field border px-3.5 py-2.5 text-start transition-colors",
    isChosen ? "border-accent bg-accent/5" : "border-base-300 bg-base-100",
    !disabled && !isChosen && "hover:border-accent/40 hover:bg-accent/5",
  );

  const body = (
    <>
      {select === "multi" ? (
        <span
          aria-hidden
          className={cn(
            "grid size-4.5 flex-none place-items-center rounded-sm border",
            isChosen
              ? "border-accent bg-accent text-accent-content"
              : "border-base-300",
          )}
        >
          {isChosen && <Check className="size-3" />}
        </span>
      ) : (
        <span
          aria-hidden
          className={cn(
            "grid size-5 flex-none place-items-center rounded-full text-micro font-bold",
            isChosen
              ? "bg-accent text-accent-content"
              : "bg-accent/10 text-accent",
          )}
        >
          {index + 1}
        </span>
      )}

      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="text-control leading-tight font-bold">
          {option.label}
        </span>
        {option.description && (
          <span className="text-note text-base-content/60">
            {option.description}
          </span>
        )}
      </span>

      {option.badge ? (
        <span className="badge badge-soft badge-accent badge-sm flex-none rounded-full border-none text-micro font-bold uppercase">
          {option.badge}
        </span>
      ) : (
        !disabled &&
        select === "single" && (
          <ChevronRight
            aria-hidden
            className="size-3.5 flex-none text-base-content/40"
          />
        )
      )}
    </>
  );

  return (
    <li>
      {disabled ? (
        <div className={className}>{body}</div>
      ) : (
        <button
          type="button"
          onClick={onSelect}
          aria-pressed={select === "multi" ? isChosen : undefined}
          className={className}
        >
          {body}
        </button>
      )}
    </li>
  );
}

/**
 * Renders one elicitation. Dumb by design: it reaches no hook and no transport,
 * and it never writes `block.status` — whether it is answerable comes in as
 * props, from the server's status plus its position in the transcript.
 *
 * Single-select submits on tap; multi-select needs an explicit confirm, because
 * there is no other way to know the user is finished.
 */
export function OptionsBlockCard({
  block,
  interactive,
  submission,
  onAnswer,
}: OptionsBlockCardProps) {
  const [selected, setSelected] = useState<string[]>([]);
  const [customText, setCustomText] = useState("");
  const promptId = useId();

  const busy = submission?.state === "submitting";
  const locked = !interactive || block.status !== "pending";
  const disabled = locked || busy;
  const recorded = block.answer;
  const hint = hintFor(block, interactive);

  // What the rows draw as chosen: the server's record once closed, the tap in
  // flight while it lands, and the local draft the rest of the time.
  const chosenIds = locked
    ? (recorded?.selectedOptionIds ?? [])
    : busy
      ? (submission?.optionIds ?? [])
      : selected;

  const answer = (optionIds: string[], text = "") =>
    onAnswer(block, { optionIds, customText: text });

  // Both modes stage a draft and send on confirm — nothing reaches the agent
  // on a stray tap. Single replaces the selection; multi toggles it.
  const choose = (optionId: string) =>
    setSelected((previous) => {
      if (block.select === "single") {
        return previous.includes(optionId) ? [] : [optionId];
      }
      return previous.includes(optionId)
        ? previous.filter((id) => id !== optionId)
        : [...previous, optionId];
    });

  // The design's "press 1–9". Scoped to the one answerable card and ignored
  // while a field has focus, so neither the inline answer nor the composer is
  // ever hijacked.
  useEffect(() => {
    if (disabled) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTyping(event.target)) return;
      const index = Number(event.key) - 1;
      const option = block.options[index];
      if (!Number.isInteger(index) || !option) return;
      event.preventDefault();
      choose(option.id);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  const canSendCustom = customText.trim().length > 0 && !disabled;

  return (
    <div className="flex flex-col gap-2.5" role="group" aria-labelledby={promptId}>
      <p id={promptId} className="text-body">
        {block.prompt}
      </p>

      <ul className="flex flex-col gap-1.5">
        {block.options.map((option, index) => (
          <OptionRow
            key={option.id}
            option={option}
            index={index}
            select={block.select}
            isChosen={chosenIds.includes(option.id)}
            disabled={disabled}
            onSelect={() => choose(option.id)}
          />
        ))}
      </ul>

      {!locked && (
        <button
          type="button"
          disabled={disabled || selected.length === 0}
          onClick={() => answer(selected)}
          className="btn btn-primary btn-sm self-start rounded-field"
        >
          {COPY.confirm}
          {block.select === "multi" && selected.length > 0 && ` ${selected.length}`}
        </button>
      )}

      {/* A typed answer stays tied to this question: it goes out as the same
          options_response the rows do, carrying custom_text instead of ids. */}
      {block.allowCustom &&
        (locked
          ? recorded?.customText && (
              <p className="text-body text-base-content/70 italic">
                {recorded.customText}
              </p>
            )
          : !busy && (
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={customText}
                  disabled={disabled}
                  maxLength={chatLimits.maxMessageLength}
                  placeholder={block.customPlaceholder ?? COPY.customFallback}
                  aria-label={`Your own answer to: ${block.prompt}`}
                  onChange={(event) => setCustomText(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key !== "Enter") return;
                    event.preventDefault();
                    if (canSendCustom) answer([], customText);
                  }}
                  className="input input-sm h-9 flex-1 rounded-field border-base-300 bg-base-100 text-note"
                />
                <button
                  type="button"
                  disabled={!canSendCustom}
                  aria-label={COPY.send}
                  onClick={() => answer([], customText)}
                  className="btn btn-square btn-sm btn-ghost size-9 rounded-field text-base-content/50"
                >
                  <Send className="size-3.5" />
                </button>
              </div>
            ))}

      {busy && <span className="loading loading-dots loading-sm text-accent" />}

      {!locked && !busy && (
        <span className="text-note text-base-content/50">
          {block.select === "single" ? COPY.singleHint : COPY.multiHint}
        </span>
      )}
      {hint && <span className="text-note text-base-content/50">{hint}</span>}
      {submission?.state === "failed" && (
        <span className="text-note text-error">{submission.error}</span>
      )}
    </div>
  );
}
