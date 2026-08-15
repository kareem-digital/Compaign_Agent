import { BrandMark } from "@/components/icons";

/** Matches the agent's turn layout so the reply lands where the dots were. */
export function TypingIndicator() {
  return (
    <div className="flex gap-3" aria-live="polite" aria-label="VOW Agent is typing">
      <BrandMark className="mt-0.5 size-6.5 flex-none" />
      <span className="loading loading-dots loading-sm text-base-content/40" />
      <span className="sr-only">Thinking…</span>
    </div>
  );
}
