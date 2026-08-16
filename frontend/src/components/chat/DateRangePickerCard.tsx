import { useState, useId } from "react";
import { Check } from "@/components/icons";
import type { ElicitationSubmission } from "@/hooks/use-chat";
import type { DraftSelection } from "@/lib/chat";
import type { DatePickerBlock } from "@/types/chat";

interface DateRangePickerCardProps {
  block: DatePickerBlock;
  interactive: boolean;
  submission?: ElicitationSubmission;
  onAnswer: (block: any, draft: DraftSelection) => void;
}

export function DateRangePickerCard({
  block,
  interactive,
  submission,
  onAnswer,
}: DateRangePickerCardProps) {
  const today = new Date().toISOString().split("T")[0];
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const promptId = useId();

  const busy = submission?.state === "submitting";
  const locked = !interactive || block.status !== "pending";
  const disabled = locked || busy;

  // Validation
  const isPast = Boolean(startDate && startDate < today);
  const isInvalidOrder = Boolean(startDate && endDate && endDate <= startDate);
  const isValid = Boolean(startDate && endDate && !isPast && !isInvalidOrder);

  const handleConfirm = () => {
    if (!isValid || disabled) return;
    onAnswer(block, {
      optionIds: [`${startDate} to ${endDate}`],
      customText: `${startDate} to ${endDate}`,
    });
  };

  const recordedAnswer = block.answer?.customText || block.answer?.selectedOptionIds?.[0];

  return (
    <section
      aria-labelledby={promptId}
      className="rounded-box border border-base-300/50 bg-base-100 p-4 shadow-card flex flex-col gap-4 max-w-lg"
    >
      <div>
        <h3 id={promptId} className="text-body font-bold text-base-content">
          {block.prompt || "When should the campaign run?"}
        </h3>
        <p className="text-note text-base-content/60 mt-0.5">
          Select the flight start and end dates (past dates are disabled).
        </p>
      </div>

      {/* Date Pickers Grid */}
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1.5">
          <label className="text-micro font-bold uppercase tracking-label text-base-content/60">
            Start Date
          </label>
          <input
            type="date"
            min={today}
            disabled={disabled}
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="input input-sm border-base-300 bg-base-100 rounded-field font-medium w-full text-control focus:border-accent focus:outline-none"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-micro font-bold uppercase tracking-label text-base-content/60">
            End Date
          </label>
          <input
            type="date"
            min={startDate || today}
            disabled={disabled}
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="input input-sm border-base-300 bg-base-100 rounded-field font-medium w-full text-control focus:border-accent focus:outline-none"
          />
        </div>
      </div>

      {/* Real-time Validation Warnings */}
      {isPast && (
        <p className="text-micro text-error font-medium">
          Start date cannot be in the past. Campaign must start on or after today.
        </p>
      )}
      {isInvalidOrder && (
        <p className="text-micro text-error font-medium">
          End date must be after the start date.
        </p>
      )}

      {/* Action footer */}
      {!locked ? (
        <div className="flex justify-end pt-1">
          <button
            type="button"
            disabled={!isValid || disabled}
            onClick={handleConfirm}
            className="btn btn-sm btn-primary rounded-field font-bold px-4 flex items-center gap-1.5"
          >
            <Check className="size-4" />
            <span>Confirm Flight Dates</span>
          </button>
        </div>
      ) : (
        recordedAnswer && (
          <div className="text-note text-base-content/70 font-semibold bg-accent/5 rounded-field p-2 border border-accent/20">
            Selected: {recordedAnswer}
          </div>
        )
      )}
    </section>
  );
}
