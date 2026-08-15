/** Domain types for the strategy plan panel. Transport-agnostic and
 *  serializable, like `types/chat.ts` — the panel renders these, never a
 *  backend payload. */

export type PlanStatus = "draft" | "approved" | "launched";

/** `locked` is the only status that changes a card's frame rather than its tag:
 *  the stage is not reachable yet, so it renders dashed and inert. */
export type StageStatus =
  | "in-progress"
  | "complete"
  | "next"
  | "optional"
  | "needs-input"
  | "locked"
  | "pending";

export interface StageProperty {
  label: string;
  /** `null` renders the design's em-dash placeholder. */
  value: string | null;
}

export interface PlanStage {
  id: string;
  title: string;
  status: StageStatus;
  /** Only the open stage shows its body; the rest rest as a single header row. */
  isOpen?: boolean;
  properties?: StageProperty[];
  /** Trailing hint on a resting or locked card ("Once approved"). */
  hint?: string;
}

export interface ReachStat {
  label: string;
  value: string;
}

/** Curve points are normalised to 0–1 with the origin at the bottom-left, so
 *  the chart owns every pixel and the data stays unit-free. */
export interface ReachPoint {
  x: number;
  y: number;
}

export interface ReachForecast {
  stats: ReachStat[];
  curve: ReachPoint[];
  /** Fraction of the y-axis the addressable ceiling sits at. */
  ceiling: number;
  ceilingLabel: string;
  peakLabel: string;
  axisLabels: { x: string; y: string };
  xTicks: string[];
  /** Bottom-to-top, matching the axis. */
  yTicks: string[];
  updatedLabel: string;
}

export interface StrategyPlan {
  name: string;
  status: PlanStatus;
  /** 0–100. Drives the panel's progress bar and the Accept Plan affordance. */
  completion: number;
  stages: PlanStage[];
  /** Rendered under the "unlocks after approval" rule. */
  lockedStages: PlanStage[];
  /** `null` until every prerequisite stage is settled. */
  forecast: ReachForecast | null;
}
