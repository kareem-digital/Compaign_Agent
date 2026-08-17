import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const auth = vi.hoisted(() => ({
  getAccessToken: vi.fn().mockResolvedValue("access-token"),
  getUser: vi.fn(),
  removeUser: vi.fn().mockResolvedValue(undefined),
  signinSilent: vi.fn(),
  startOAuthRedirect: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("@/lib/auth", () => ({
  createOidcUserManager: () => ({
    getUser: auth.getUser,
    removeUser: auth.removeUser,
    signinSilent: auth.signinSilent,
  }),
  OAuthAccessTokenProvider: class {
    getAccessToken = auth.getAccessToken;
  },
  startOAuthRedirect: auth.startOAuthRedirect,
}));

vi.mock("@/widget", () => ({
  VowAgentWidget: () => <div>Authenticated VOW Agent</div>,
}));

import App from "@/App";
import { config } from "@/lib/config";

describe("standalone App authentication", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/agent/");
    config.authMode = "oidc";
    auth.getUser.mockReset().mockResolvedValue(null);
    auth.removeUser.mockClear();
    auth.signinSilent.mockReset();
    auth.startOAuthRedirect.mockClear();
  });

  it("shows Sign in with VOW before starting the redirect flow", async () => {
    render(<App />);

    const signIn = await screen.findByRole("button", {
      name: "Sign in with VOW",
    });
    fireEvent.click(signIn);

    await waitFor(() =>
      expect(auth.startOAuthRedirect).toHaveBeenCalledWith(
        config.oauth,
        expect.anything(),
        "/agent/",
      ),
    );
    expect(screen.queryByText("Authenticated VOW Agent")).not.toBeInTheDocument();
  });

  it("renders the agent when a valid stored user is restored", async () => {
    auth.getUser.mockResolvedValue({ expired: false });

    render(<App />);

    expect(await screen.findByText("Authenticated VOW Agent")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign in with VOW" })).toBeNull();
  });

  it("renews an expired stored user before rendering the agent", async () => {
    auth.getUser.mockResolvedValue({
      expired: true,
      refresh_token: "refresh-token",
    });
    auth.signinSilent.mockResolvedValue({ expired: false });

    render(<App />);

    expect(await screen.findByText("Authenticated VOW Agent")).toBeInTheDocument();
    expect(auth.signinSilent).toHaveBeenCalledWith({
      resource: config.oauth.resource,
    });
  });

  it("renders immediately without OIDC when local authentication is enabled", () => {
    config.authMode = "local";

    render(<App />);

    expect(screen.getByText("Authenticated VOW Agent")).toBeInTheDocument();
    expect(auth.getUser).not.toHaveBeenCalled();
    expect(auth.startOAuthRedirect).not.toHaveBeenCalled();
  });
});
