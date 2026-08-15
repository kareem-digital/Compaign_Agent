import { cn } from "@/lib/utils";
import type { StageStatus } from "@/types/strategy";

const COPY: Record<StageStatus, string | null> = {
  "in-progress": "In progress",
  complete: "Complete",
  next: "Next",
  optional: "Optional",
  "needs-input": "Needs input",
  locked: null,
  pending: null,
};

/* `next` is the one status the design draws as bare text rather than a pill —
 * it is a hint about what follows, not a state the stage is in. */
const TONE: Record<StageStatus, string> = {
  "in-progress": "badge-accent",
  complete: "badge-success",
  next: "",
  optional: "badge-neutral",
  "needs-input": "badge-warning",
  locked: "",
  pending: "",
};

interface StageStatusBadgeProps {
  status: StageStatus;
  className?: string;
}

export function StageStatusBadge({ status, className }: StageStatusBadgeProps) {
  const label = COPY[status];
  if (!label) return null;

  if (status === "next") {
    return (
      <span className={cn("text-note text-base-content/50", className)}>
        {label}
      </span>
    );
  }

  return (
    <span
      className={cn(
        "badge badge-soft badge-sm rounded-full border-none text-micro font-bold uppercase",
        TONE[status],
        className,
      )}
    >
      {label}
    </span>
  );
}
