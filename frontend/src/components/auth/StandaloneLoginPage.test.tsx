import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { StandaloneLoginPage } from "./StandaloneLoginPage";

describe("StandaloneLoginPage", () => {
  it("starts VOW sign-in from an explicit user action", () => {
    const onSignIn = vi.fn();
    render(<StandaloneLoginPage isSigningIn={false} onSignIn={onSignIn} />);

    fireEvent.click(screen.getByRole("button", { name: "Sign in with VOW" }));

    expect(onSignIn).toHaveBeenCalledOnce();
  });

  it("shows redirect progress and authentication errors", () => {
    render(
      <StandaloneLoginPage
        error="VOW sign-in could not be started."
        isSigningIn
        onSignIn={() => undefined}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "VOW sign-in could not be started.",
    );
    expect(screen.getByRole("button", { name: "Redirecting to VOW…" })).toBeDisabled();
  });
});
