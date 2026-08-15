import { Clock, Plus } from "@/components/icons";
import { cn } from "@/lib/utils";

const RAIL_ACTIONS = [
  { key: "new", label: "New strategy", Icon: Plus },
  { key: "recent", label: "Recent strategies", Icon: Clock },
] as const;

interface NavRailProps {
  className?: string;
}

/**
 * The inline-start icon rail. Intentionally inert for now — the navigation
 * behind these controls has not been built, so they carry labels and hit areas
 * but no handlers.
 *
 * The `before:` inset widens each 36px target to the 44px minimum without
 * disturbing the rail's spacing.
 */
export function NavRail({ className }: NavRailProps) {
  return (
    <nav
      aria-label="VOW Agent"
      className={cn(
        "flex w-15 flex-none flex-col items-center gap-2.5 border-e border-base-300/60 pt-5",
        className,
      )}
    >
      <span
        aria-hidden
        className="grid size-9 place-items-center rounded-selector bg-primary/10 text-control font-semibold text-base-content/70"
      >
        »
      </span>

      {RAIL_ACTIONS.map(({ key, label, Icon }) => (
        <button
          key={key}
          type="button"
          aria-label={label}
          className="relative grid size-9 place-items-center rounded-selector border border-base-300/60 text-base-content/70 before:absolute before:-inset-1 hover:border-primary/40 hover:text-primary"
        >
          <Icon className="size-4" />
        </button>
      ))}
    </nav>
  );
}
