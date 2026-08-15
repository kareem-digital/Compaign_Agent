import type { StageProperty } from "@/types/strategy";

const EMPTY = "—";

interface PropertyRowsProps {
  properties: StageProperty[];
}

/**
 * The label→value grid three stages share (basic details, goals, the extra
 * targeting block). A fixed label column rather than `justify-between` so the
 * values line up down the card even when a label wraps.
 */
export function PropertyRows({ properties }: PropertyRowsProps) {
  return (
    <dl className="flex flex-col gap-2.5">
      {properties.map(({ label, value }) => (
        <div key={label} className="flex gap-3.5">
          <dt className="w-23 flex-none text-micro font-bold uppercase tracking-label text-base-content/50">
            {label}
          </dt>
          <dd
            className={
              value
                ? "flex-1 text-note font-semibold text-base-content"
                : "flex-1 text-note text-base-content/40"
            }
          >
            {value ?? EMPTY}
          </dd>
        </div>
      ))}
    </dl>
  );
}
