import { cn } from "@/lib/utils";
import type { PlanStatus } from "@/types/strategy";

const STATUS_COPY: Record<PlanStatus, string> = {
  draft: "Draft",
  approved: "Approved",
  launched: "Launched",
};

const STATUS_TONE: Record<PlanStatus, string> = {
  draft: "badge-accent",
  approved: "badge-success",
  launched: "badge-primary",
};

interface WorkspaceHeaderProps {
  name: string;
  status: PlanStatus;
  className?: string;
}

/** The chat console's title bar: which strategy is open, and where it stands. */
export function WorkspaceHeader({
  name,
  status,
  className,
}: WorkspaceHeaderProps) {
  return (
    <header
      className={cn(
        "flex h-(--workspace-header-height) flex-none items-center gap-2.5 border-b border-base-300/60 bg-base-100 px-8",
        className,
      )}
    >
      <h1 className="text-lg font-bold text-base-content">{name}</h1>
      <span
        className={cn(
          "badge badge-soft badge-sm rounded-full border-none text-micro font-bold uppercase",
          STATUS_TONE[status],
        )}
      >
        {STATUS_COPY[status]}
      </span>
    </header>
  );
}
