# Frontend test layout

Authoritative source for tooling: `Calyxio_VOW_QA_Testing_Reporting_Strategy.pdf`
(see `backend/tests/README.md` for the full layer-to-tool table). The one
layer that lives entirely in this package is:

| PDF layer (§1) | Primary tool | Notes |
|---|---|---|
| UI E2E | **Playwright** | trader/user journeys; screenshots/video/trace on failure (§10) |

Backend's "Workflow" layer (`backend/tests/workflow/`, pytest + Allure) covers
the same Golden Path end to end but through the API/agent layer directly, no
browser — the two are complementary, not duplicates.

Component/hook/unit tests stay **co-located** next to the source they cover
(`ChatInput.test.tsx` beside `ChatInput.tsx`, `use-chat.test.tsx` beside
`use-chat.ts`, etc.) — that's already the convention in `src/` and is the
idiomatic Vitest/Testing-Library pattern. Don't move those here.

This `tests/` tree is for suites that don't belong next to a single source
file — cross-cutting or full-stack:

```
tests/
    e2e/          Playwright, browser-driven, against a running frontend + backend
    integration/  multi-component flows (widget + chat + mocked backend via MSW), not tied to one file
    mocks/        shared MSW request handlers / mock server reused by integration and e2e
    fixtures/     sample API payloads, chat transcripts
    helpers/      custom render() with providers, shared test utilities
```

`helpers/` here serves suites in **this** tree only. Helpers for the co-located
unit tests live in **`src/test/`** instead (`render.tsx`, `factories.ts`),
because `tsconfig.app.json` has `"include": ["src"]` — anything under `tests/`
is outside the app TS project, so `@/…` does not resolve to it and
`npm run typecheck` would not see it. Adding `"tests"` to that include would
drag `tests/e2e/` in, and its `@playwright/test` import breaks the typecheck
until Playwright is installed. `src/test/**` is excluded from coverage in
`vite.config.ts`.

## Coverage

`npm run test:coverage` runs Vitest with the v8 provider and enforces the
thresholds in `vite.config.ts`. CI runs the same command, so a drop below the
threshold fails the PR. Thresholds are ratcheted up in the same change as the
tests that earn them — never set aspirationally, or the gate is decoration.

## Current state

`e2e/` is a placeholder: this repo does not have Playwright installed yet.
`playwright.config.ts` has been added at the frontend root (`testDir` points
here, and captures `screenshot: "only-on-failure"` / `video: "retain-on-failure"`
per the PDF's UI reporting requirement). You still need to run, locally:

```bash
npm install -D @playwright/test
npx playwright install
```

before `npm run test:e2e` will do anything. CI (`.github/workflows/ci-frontend.yml`)
has **not** been touched to add an e2e job — wire that up once real specs
exist, so CI doesn't fail on an empty/unbuilt suite.

`integration/`, `mocks/`, `fixtures/`, and `helpers/` are also empty right
now: the only backend surface today is `/api/v1/health/*` and
`/api/v1/sessions/chat` (see `src/lib/agent/http-agent-client.ts` and
`src/lib/agent/mock-agent-client.ts`, which already gives you a swappable
fake agent client for integration-style component tests without a real
backend). The application workflow UI these will eventually exercise (PDF
§9): Brief -> Planning -> Strategies -> Forecast -> Approval -> Activation ->
Delivery — none of which exist as UI yet beyond the current chat widget.
