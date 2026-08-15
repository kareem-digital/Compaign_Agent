import { useId, type ReactNode } from "react";

import { ChevronDown, ChevronRight, Lock } from "@/components/icons";
import { StageStatusBadge } from "@/components/strategy/StageStatusBadge";
import { cn } from "@/lib/utils";
import type { PlanStage } from "@/types/strategy";

interface StageCardProps {
  stage: PlanStage;
  onToggle?: (id: string) => void;
  children?: ReactNode;
}

/**
 * The one card shell every stage wears. Only the *body* differs between
 * stages, so the header — chevron, title, status tag, trailing hint or lock —
 * lives here once and each stage passes its own content as children.
 *
 * A locked stage is inert: it drops to a dashed frame, loses its status tag and
 * never renders a body, so it gets no button and no expanded state.
 */
export function StageCard({ stage, onToggle, children }: StageCardProps) {
  const bodyId = useId();
  const { id, title, status, isOpen = false, hint } = stage;
  const isLocked = status === "locked";
  const Chevron = isOpen ? ChevronDown : ChevronRight;

  const header = (
    <>
      <Chevron
        className={cn(
          "size-3.5 flex-none",
          isLocked
            ? "text-base-content/25"
            : isOpen
              ? "text-accent"
              : "text-base-content/40",
        )}
      />
      <span
        className={cn(
          "flex-1 text-start text-card-title font-bold",
          isLocked
            ? "text-base-content/40"
            : isOpen
              ? "text-base-content"
              : "text-base-content/70",
        )}
      >
        {title}
      </span>
      <StageStatusBadge status={status} />
      {hint && <span className="text-note text-base-content/50">{hint}</span>}
      {isLocked && <Lock className="size-3.5 flex-none text-base-content/25" />}
    </>
  );

  return (
    <li
      className={cn(
        "card card-border rounded-field border-base-300/50 bg-base-100",
        isLocked ? "border-dashed bg-base-100/50" : "shadow-card",
      )}
    >
      <div className="card-body gap-3 p-4">
        {isLocked || !onToggle ? (
          <div className="flex items-center gap-2.5">{header}</div>
        ) : (
          <button
            type="button"
            aria-expanded={isOpen}
            aria-controls={children ? bodyId : undefined}
            onClick={() => onToggle(id)}
            className="flex items-center gap-2.5 text-start"
          >
            {header}
          </button>
        )}

        {isOpen && children && <div id={bodyId}>{children}</div>}
      </div>
    </li>
  );
}
