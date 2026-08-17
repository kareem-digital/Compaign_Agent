import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AgentClient } from "@/lib/agent";
import { textBlock } from "@/lib/chat";
import { config } from "@/lib/config";
import { makeOptionsBlock, stubAgentClient } from "@/test/factories";
import { VowAgentWidget } from "@/widget/VowAgentWidget";

/**
 * The surface a host consumes through Module Federation. Every dependency
 * arrives as a prop and the widget supplies its own AgentClientProvider, so
 * these render it directly — no wrapper, no module mocking.
 */
beforeEach(() => {
  // The widget logs the `user` prop in dev; keep it out of the test output.
  vi.spyOn(console, "log").mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("VowAgentWidget", () => {
  it("routes messages through the transport the host supplies", async () => {
    // The most important assertion here: a host's override has to survive the
    // whole AgentClientProvider -> useChat -> ChatContainer chain.
    const user = userEvent.setup();
    const agentClient = stubAgentClient("Here is a plan.");
    render(<VowAgentWidget agentClient={agentClient} />);

    await user.type(
      screen.getByLabelText("Message VOW Agent"),
      "Plan a CTV campaign{Enter}",
    );

    expect(await screen.findByText("Here is a plan.")).toBeInTheDocument();
    expect(agentClient.send).toHaveBeenCalledWith(
      expect.objectContaining({
        content: [{ type: "text", text: "Plan a CTV campaign" }],
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it("carries a tapped answer all the way back to the transport", async () => {
    // The full chain a host depends on: provider -> useChat -> ChatWorkspace ->
    // MessageBubble -> OptionsBlockCard, and the answer back out again.
    const user = userEvent.setup();
    const question = makeOptionsBlock();
    const send = vi
      .fn<AgentClient["send"]>()
      .mockResolvedValueOnce({ content: [question] })
      .mockResolvedValueOnce({ content: [textBlock("Noted.")] });
    render(<VowAgentWidget agentClient={{ send }} />);

    await user.type(
      screen.getByLabelText("Message VOW Agent"),
      "Plan a CTV campaign{Enter}",
    );

    await user.click(
      await screen.findByRole("button", { name: /Prime Video/ }),
    );
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    expect(await screen.findByText("Noted.")).toBeInTheDocument();
    expect(send.mock.calls[1][0].content).toEqual([
      {
        type: "options_answer",
        elicitationId: question.id,
        selectedOptionIds: ["opt-prime"],
        customText: null,
      },
    ]);
  });

  it("shows the strategy panel once a conversation exists", async () => {
    const user = userEvent.setup();
    render(<VowAgentWidget agentClient={stubAgentClient("Here is a plan.")} />);

    expect(
      screen.queryByRole("complementary", { name: "Strategy plan" }),
    ).not.toBeInTheDocument();

    await user.type(
      screen.getByLabelText("Message VOW Agent"),
      "Plan a CTV campaign{Enter}",
    );

    expect(
      await screen.findByRole("complementary", { name: "Strategy plan" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "VOW Agent" })).toBeInTheDocument();
  });

  it("opens on the start screen rather than a transcript", () => {
    render(<VowAgentWidget agentClient={stubAgentClient()} />);

    expect(
      screen.getByRole("heading", { name: "Start planning" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("log")).not.toBeInTheDocument();
  });

  it("accepts title and tagline without rendering them", () => {
    // Documented as accepted-but-unconsumed: the start screen has no title bar,
    // so a host can wire these ahead of the conversation view landing.
    render(
      <VowAgentWidget
        agentClient={stubAgentClient()}
        title="Acme Planner"
        tagline="Powered by VOW"
      />,
    );

    expect(screen.queryByText("Acme Planner")).not.toBeInTheDocument();
    expect(screen.queryByText("Powered by VOW")).not.toBeInTheDocument();
    expect(screen.queryByText(config.appTagline)).not.toBeInTheDocument();
  });

  it("applies the requested daisyUI theme to its own subtree", () => {
    const { container } = render(
      <VowAgentWidget agentClient={stubAgentClient()} theme="dark" />,
    );

    expect(container.querySelector("section")).toHaveAttribute(
      "data-theme",
      "dark",
    );
  });

  it("leaves data-theme unset so an embedded widget inherits the host page's theme", () => {
    const { container } = render(
      <VowAgentWidget agentClient={stubAgentClient()} />,
    );

    expect(container.querySelector("section")).not.toHaveAttribute("data-theme");
  });

  it("appends the host's className to its own layout classes", () => {
    // Sizing and placement are the host's call; the widget must not lose its
    // own flex chain in the process.
    const { container } = render(
      <VowAgentWidget agentClient={stubAgentClient()} className="h-dvh" />,
    );

    const section = container.querySelector("section");
    expect(section).toHaveClass("h-dvh");
    expect(section).toHaveClass("flex-1");
    expect(section).toHaveClass("bg-base-200");
  });

  it("accepts a user prop without rendering it, ahead of the session contract", () => {
    // Documented as accepted-but-unconsumed — a host can wire it today.
    render(
      <VowAgentWidget
        agentClient={stubAgentClient()}
        user={{ id: "u-1", email: "trader@example.test", name: "Sam" }}
      />,
    );

    expect(screen.queryByText("trader@example.test")).not.toBeInTheDocument();
    expect(screen.queryByText("Sam")).not.toBeInTheDocument();
  });

  it("reaches the HTTP transport by default when no client is given", async () => {
    const fetchImpl = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            session_id: "s-1",
            reply: "from the server",
            stage: null,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
    );
    vi.stubGlobal("fetch", fetchImpl);

    const user = userEvent.setup();
    render(
      <VowAgentWidget
        advertiserId="adv-1"
        accessToken={async () => "access-token"}
      />,
    );

    await user.type(
      screen.getByLabelText("Message VOW Agent"),
      "Plan a CTV campaign{Enter}",
    );

    expect(await screen.findByText("from the server")).toBeInTheDocument();
    expect(fetchImpl).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer access-token",
          "Vowmade-Advertiser-Id": "adv-1",
        }),
      }),
    );

    vi.unstubAllGlobals();
  });
});
