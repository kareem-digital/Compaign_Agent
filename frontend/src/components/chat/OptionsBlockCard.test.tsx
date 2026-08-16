import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { OptionsBlockCard } from "@/components/chat/OptionsBlockCard";
import type { OptionsBlock } from "@/types/chat";
import { makeOptionsBlock } from "@/test/factories";

function renderCard(
  block: OptionsBlock,
  overrides: Partial<
    Omit<React.ComponentProps<typeof OptionsBlockCard>, "block">
  > = {},
) {
  const onAnswer = vi.fn();
  const result = render(
    <OptionsBlockCard
      block={block}
      interactive
      onAnswer={onAnswer}
      {...overrides}
    />,
  );
  return { onAnswer, ...result };
}

const row = (label: string | RegExp) =>
  screen.getByRole("button", { name: label });

describe("OptionsBlockCard", () => {
  it("labels the question group with its prompt", () => {
    const block = makeOptionsBlock();
    renderCard(block);

    expect(
      screen.getByRole("group", { name: block.prompt }),
    ).toBeInTheDocument();
    expect(screen.getByText("Live sport and gaming")).toBeInTheDocument();
    expect(screen.getByText("Suggested")).toBeInTheDocument();
  });

  it("stages a single choice and sends it only on confirm", async () => {
    const user = userEvent.setup();
    const block = makeOptionsBlock();
    const { onAnswer } = renderCard(block);

    await user.click(row(/Prime Video/));
    // Nothing reaches the agent on a stray tap.
    expect(onAnswer).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Confirm" }));

    expect(onAnswer).toHaveBeenCalledWith(block, {
      optionIds: ["opt-prime"],
      customText: "",
    });
  });

  it("replaces the staged choice for a single-select", async () => {
    const user = userEvent.setup();
    const block = makeOptionsBlock();
    const { onAnswer } = renderCard(block);

    await user.click(row(/Prime Video/));
    await user.click(row(/Twitch/));
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    expect(onAnswer).toHaveBeenCalledWith(block, {
      optionIds: ["opt-twitch"],
      customText: "",
    });
  });

  it("toggles choices for a multi-select and counts them on the confirm", async () => {
    const user = userEvent.setup();
    const block = makeOptionsBlock({ select: "multi" });
    const { onAnswer } = renderCard(block);

    await user.click(row(/Prime Video/));
    await user.click(row(/Twitch/));
    expect(row(/Prime Video/)).toHaveAttribute("aria-pressed", "true");

    // Tapping again removes it rather than replacing the set.
    await user.click(row(/Twitch/));
    await user.click(screen.getByRole("button", { name: "Confirm 1" }));

    expect(onAnswer).toHaveBeenCalledWith(block, {
      optionIds: ["opt-prime"],
      customText: "",
    });
  });

  it("keeps confirm disabled until something is staged", async () => {
    const user = userEvent.setup();
    renderCard(makeOptionsBlock());

    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();

    await user.click(row(/Prime Video/));

    expect(screen.getByRole("button", { name: "Confirm" })).toBeEnabled();
  });

  it("stages a choice from the 1–9 shortcut", async () => {
    const user = userEvent.setup();
    const block = makeOptionsBlock();
    const { onAnswer } = renderCard(block);

    await user.keyboard("2");
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    expect(onAnswer).toHaveBeenCalledWith(block, {
      optionIds: ["opt-twitch"],
      customText: "",
    });
  });

  it("locks a question that is no longer the active one", () => {
    renderCard(makeOptionsBlock(), { interactive: false });

    expect(screen.queryByRole("button", { name: /Prime Video/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Confirm" })).toBeNull();
    expect(
      screen.getByText("Only the latest question can be answered."),
    ).toBeInTheDocument();
  });

  it("explains a superseded and an expired question", () => {
    const { unmount } = renderCard(makeOptionsBlock({ status: "superseded" }));
    expect(
      screen.getByText("We moved on from this question."),
    ).toBeInTheDocument();
    unmount();

    renderCard(makeOptionsBlock({ status: "expired" }));
    expect(
      screen.getByText("This question is no longer open."),
    ).toBeInTheDocument();
  });

  it("draws the server's recorded answer once the question is closed", () => {
    renderCard(
      makeOptionsBlock({
        status: "answered",
        answer: {
          selectedOptionIds: ["opt-twitch"],
          customText: null,
          answeredAt: null,
        },
      }),
    );

    // Locked, so the rows are static and the record is what shows.
    expect(screen.queryByRole("button", { name: /Twitch/ })).toBeNull();
  });

  it("shows the tap in flight while it lands, without locking on its own", () => {
    renderCard(makeOptionsBlock(), {
      submission: {
        clientMessageId: "c-1",
        optionIds: ["opt-prime"],
        customText: null,
        state: "submitting",
      },
    });

    // Busy disables the rows but is not a lock: no closed-question hint.
    expect(screen.queryByRole("button", { name: /Prime Video/ })).toBeNull();
    expect(
      screen.queryByText("Only the latest question can be answered."),
    ).toBeNull();
  });

  it("surfaces a failed submission's error", () => {
    renderCard(makeOptionsBlock(), {
      submission: {
        clientMessageId: "c-1",
        optionIds: ["opt-prime"],
        customText: null,
        state: "failed",
        error: "The agent could not be reached. Please try again.",
      },
    });

    expect(
      screen.getByText("The agent could not be reached. Please try again."),
    ).toBeInTheDocument();
    // Still answerable, so a retry is possible.
    expect(row(/Prime Video/)).toBeEnabled();
  });

  it("hints at the interaction each selection mode expects", () => {
    const { unmount } = renderCard(makeOptionsBlock({ select: "single" }));
    expect(screen.getByText(/Pick one/)).toBeInTheDocument();
    unmount();

    renderCard(makeOptionsBlock({ select: "multi" }));
    expect(screen.getByText(/Pick any that apply/)).toBeInTheDocument();
  });
});
