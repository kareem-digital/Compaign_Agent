/**
 * Render helpers for the co-located component tests.
 *
 * These live in `src/` rather than `tests/helpers/` because
 * `tsconfig.app.json` has `"include": ["src"]` — a helper outside that tree is
 * not part of the app project, so `@/…` would not resolve to it and
 * `npm run typecheck` would not see it. Excluded from coverage in
 * `vite.config.ts`.
 */
import {
  render,
  type RenderOptions,
  type RenderResult,
} from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";

import { AgentClientProvider, type AgentClient } from "@/lib/agent";

export interface RenderWithProvidersOptions
  extends Omit<RenderOptions, "wrapper"> {
  /**
   * Transport handed to `<AgentClientProvider>`. Omit it for components that
   * never reach the agent — no provider is mounted in that case, so a component
   * that starts calling `useAgentClient()` fails loudly instead of quietly
   * picking up a real mock client with real half-second timers.
   */
  client?: AgentClient;
}

/**
 * Mirrors the wrapper pattern in `use-chat.test.tsx`: the transport is
 * injected, never module-mocked, because that injectability is itself the
 * property under test (see CLAUDE.md, "Testing approach").
 */
export function renderWithProviders(
  ui: ReactElement,
  { client, ...options }: RenderWithProvidersOptions = {},
): RenderResult {
  function Wrapper({ children }: { children: ReactNode }) {
    if (!client) return <>{children}</>;
    return <AgentClientProvider client={client}>{children}</AgentClientProvider>;
  }

  return render(ui, { wrapper: Wrapper, ...options });
}

/** `renderHook` takes a `wrapper` component rather than a render function. */
export function agentWrapper(client: AgentClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <AgentClientProvider client={client}>{children}</AgentClientProvider>;
  };
}
