# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## IMPORTANT: Docs-First Rule

Before generating any code, **always check the `/docs` directory first** for relevant documentation. If a docs file exists for the technology or feature you're working with, read it before writing any code. The `/docs` directory contains authoritative guidance that takes precedence over general knowledge:

- /docs/architecture.md — styling tokens, i18n, responsive readiness
- /docs/ui.md
- /docs/structure.md — naming, layering, and folder-placement conventions
- /docs/elicitation.md — the interactive-options wire contract and its interaction rules

## Commands

```bash
npm run dev          # dev server on http://localhost:3000
npm run mock:dev     # fixture-driven mock chat API on http://localhost:4100
npm run build        # tsc -b && vite build
npm run preview      # serve the production build
npm test             # vitest, single run
npm run test:watch   # vitest watch mode
npm run test:coverage # vitest + v8 coverage; enforces the thresholds CI gates on
npm run typecheck    # tsc -b --noEmit
npm run lint         # eslint (flat config, no args — lints the whole project)
```

Running a subset of tests:

```bash
npm test -- src/lib/api/http.test.ts        # one file
npm test -- -t "aborts an in-flight"        # by test name
```

## Repository context

This directory is the **frontend only**. The repo root (`../`) is a separate Python service — "Agentic VOW", a FastAPI + LangGraph planning agent for CTV campaigns on Amazon DSP (`uvicorn app.main:app --reload`, `pytest`, `ruff`). See `../README.md`.

- Backend serves on **http://localhost:8000** under **`/api/v1`** (`../app/config.py`); its CORS allowlist defaults to this dev server's origin.
- **Health and `POST /sessions/chat` exist today** (`../backend/app/api/`). Approvals and audit are still TODO. This is why the agent transport is an abstraction rather than inline fetch calls.
- **`mock-server/`** is a fixture-driven stand-in for that chat endpoint, so frontend work isn't blocked on the backend. `npm run mock:dev`, then point `VITE_API_BASE_URL` at `http://localhost:4100/api/v1`. See `mock-server/README.md`.
- `../Frontend_Next/` is the previous Next.js implementation, kept as **reference only**. It is not built, not deployed, and not part of this project. Its `Requirement.md` is the original product spec.

## Architecture

React 18.2 + Vite 6 SPA, TypeScript strict, path alias `@/*` → `./src/*`. The app runs standalone today and is shaped to become a Module Federation remote without a refactor.

### The API layer — the load-bearing design

Everything reaching the backend goes through one boundary:

```
components → use-chat → useAgentClient() → AgentClient → http-agent-client → http.ts
                         (context)          (contract)                       (transport)
```

- **`lib/api/http.ts`** is the only place `fetch` is called. It owns base-URL resolution, JSON handling, per-request timeouts, the `X-Request-ID` correlation header, and normalizing failures into a typed `ApiError`. Caller aborts are re-thrown untouched — cancellation is control flow, not an error, and `use-chat` relies on that.
- **`lib/agent/types.ts`** defines `AgentClient`. This contract does not change when the backend lands.
- **`createAgentClient(config)`** selects an implementation; **`AgentClientProvider`** supplies it through context.

Three rules follow from this, and violating them is the main way to break the design:

1. **Never export or import an `agentClient` singleton.** The previous app did exactly that (`Frontend_Next/src/lib/agent/index.ts`), which fixed the transport at import time and made it impossible to stub or inject. `lib/agent/index.ts` is a barrel only.
2. **Components and hooks never call `fetch` directly** — they go through a service built on `http.ts`.
3. **`createHttpAgentClient` owns the wire format.** It maps `AgentRequest`/`AgentReply` to `POST /sessions/chat`, whose snake_case shapes live in `lib/agent/wire.ts` — type-only, imported by that one file and deliberately absent from the barrel, so the boundary is enforced by the import graph. `AgentRequest` carries no `history`: the backend keeps conversation state server-side keyed by `session_id`, so one client instance is one conversation. That id is currently **minted by the client** (`createId()`, once per instance) and sent on every turn, because the endpoint that issues one isn't live yet — as is the hardcoded `Vowmade-Advertiser-Id` header the backend requires. Both are marked TEMP in `http-agent-client.ts`. It's the only `AgentClient` implementation — `createAgentClient` always builds it. There is no in-process mock; switching between `mock-server/` (`http://localhost:4100/api/v1`, the default) and the real backend (`:8000`, once its sessions router lands) is purely `VITE_API_BASE_URL`.

A turn is a **list of blocks**, not a string: `text`, an agent `options` question, or the user's `options_answer`. That's what lets a reply be prose, a single-select or a multi-select. Two rules from `/docs/elicitation.md` are easy to break from the UI side and worth repeating here: an option's model-facing `value` never crosses the boundary (the mapper copies option fields one at a time rather than spreading, so a server that sends it anyway has it dropped), and an elicitation's `status` is **server-owned** — the client renders it, never derives it, and an unrecognised value narrows to `expired` so a dead row can't look answerable.

Request/response ↔ domain mapping belongs in `http-agent-client.ts` and nowhere else, so the UI stays ignorant of the wire format.

### Testing approach

Tests inject the transport through `AgentClientProvider` rather than `vi.mock`-ing modules — that injectability is itself the property under test. `http.ts` takes a `fetchImpl` option for the same reason. See `src/hooks/use-chat.test.tsx` for the wrapper pattern.

### Styling

**Tailwind v4 + daisyUI v5**, configured CSS-first. There is no `tailwind.config.ts` — `@plugin`, `@theme` and `@source` live in the CSS entry points, and `postcss.config.js` runs `@tailwindcss/postcss` (no `autoprefixer`; v4 prefixes internally).

There are **two entry points**, and the difference between them is the whole embedding story:

| | `src/index.css` | `src/widget/widget.css` |
|---|---|---|
| used by | standalone SPA | Module Federation remote (`?inline`) |
| Tailwind | `@import "tailwindcss"` (incl. preflight) | `theme.css` + `utilities.css` only — **no preflight** |
| daisyUI | full | `exclude: rootcolor` |
| cascade layers | normal (Tailwind default) | **none** — flattened in `postcss.config.js` |
| resets | preflight | `widget/widget-reset.css`, scoped to `.vow-agent-widget` |

Both `@import "./styles/themes.css"`, which holds the two brand themes (OKLCH) and is shared so the widget can never drift from the app.

**Why the embed build ships no cascade layers.** The host is on Tailwind 3.4 with `important: true`, and its `common/styles/index.scss` adds more raw rules — so the host's CSS is entirely unlayered. Unlayered normal declarations beat layered ones *regardless of specificity*, so while the widget was layered the host's preflight won every collision inside our own subtree: `*{border-width:0}` beat `.border` (borders vanished), `button{background:transparent}` beat `.btn-primary` (send button unfilled), `h1{font-size:inherit}` beat `.text-xl`. Unlayered, our class selectors (0,1,0) outrank the host's element (0,0,1) and universal (0,0,0) resets. `postcss.config.js` flattens the layers Tailwind and daisyUI still emit themselves, scoped to `widget.css` only.

**Flattening must reorder, not just unwrap.** Removing `@layer` throws away layer precedence, leaving source order as the only tiebreaker — and daisyUI 5's emitted order is the *opposite* of its precedence. It nests `daisyui > daisyui.l1 > daisyui.l1.l2 > daisyui.l1.l2.l3`, puts base components (`.btn`) in the deepest layer and their modifiers (`.btn-primary`, `.btn-square`, `.btn-sm`) one level up, and relies on the rule that a layer's own rules outrank its sub-layers'. In the file, the deep blocks come last. An in-place unwrap therefore let `.btn` overwrite every `.btn-*` that preceded it: `--btn-fg` fell back to `base-content`, so `btn-primary` rendered dark navy text on the primary fill, and `btn-sm`/`btn-square` lost their sizing and padding. The plugin now buckets top-level nodes by layer path, sorts by real cascade precedence — layers in declaration order at each level; a path that is a *prefix* of another ranks higher; unlayered (path `[]`) ranks highest, which is what keeps Tailwind's utilities above daisyUI's components — then emits them unwrapped, stable-sorted so ties keep source order. **Do not "simplify" this back to `replaceWith(rule.nodes)`.** Re-verify the layer shape on a daisyUI major bump; `postcss.config.js` documents the model.

Four things to keep intact when touching any of this:

1. **`themes: false` on the daisyUI plugin is load-bearing.** The theme blocks override the *built-in* `light`/`dark` by name, and daisyUI emits the built-ins into the same selectors afterwards — leaving them enabled means the stock palette silently wins. Semantic colors not defined (neutral/info/success/warning/error) are still inherited.
2. **The `.vow-agent-widget` class on the widget root is not decorative.** With preflight and `rootcolor` both compiled out of the embed build, it is the only thing applying box-sizing, the border reset and the theme's base colors inside a host page. Drop it and the widget unstyles when embedded while standalone still looks fine. It also restates `font-size`/`line-height`, which preflight would put on `html`: a host sets its own on `body` and both inherit straight through this root — VowMade's `body{font-size:14px;line-height:17px}` shrank every unsized string in the widget and crushed its leading.
3. **Use the PostCSS plugin, not `@tailwindcss/vite`.** `widget.css` is consumed as `?inline` by `widget/federated.tsx`; the PostCSS path keeps that transform working — and the layer-flattening plugin above hangs off it.
4. **`inject-styles.ts` must keep prepending.** Unlayered widget CSS competes on source order, and its utility class names also match host elements. Going first is what keeps the host winning on its own markup.

Radii come from daisyUI 5's `--radius-box`/`--radius-field`/`--radius-selector`, which generate `rounded-box`/`rounded-field`/`rounded-selector` natively — the v4→v5 `borderRadius` bridge the old config carried is gone. Fonts are self-hosted Geist via `@fontsource-variable`.

The host app (`../../VowMade/vowmade/frontend`) is on Tailwind v3.4 with `important: true`, but nothing is shared: separate lockfile, its `content` glob never scans this project, and the widget reaches it only as compiled CSS injected at runtime. The two Tailwind majors coexist and do not need to move together.

**`important: true` on the host is a hazard we cannot out-rank.** Every host utility carries `!important`, and utility class names are a shared namespace across the two Tailwind majors — so any host utility whose name we also use wins inside our subtree no matter what we do with layers, order or specificity. Measured against the current host, the overlap is `.bg-transparent`, `.font-bold`, `.font-semibold`, `.rounded-full`, `.border`, `.border-b`, `.border-t`, `.border-dashed`, `.p-4`, `.px-3/4/5/8`, `.mx-auto`, `.truncate`, `.whitespace-pre-wrap` plus layout utilities — all currently carrying values identical to ours, so nothing breaks today. If the host retunes its spacing or colour scale this silently restyles the widget, and the only real fixes are `!important` on our side or Shadow DOM. Re-run the audit when the host's Tailwind config changes.

**Diagnosing a suspected leak.** Compare against the same widget standalone rather than reasoning about the cascade: mount the subtree's `outerHTML` in an `about:blank` iframe carrying only `#vow-agent-widget-styles`, then diff `getComputedStyle` element-by-element. That isolates host influence in one pass and is what identified both the flattening bug and the `body` typography leak — neither of which the layer/specificity model predicted.

### Embedding

`widget/VowAgentWidget.tsx` is the self-contained mount point a host would consume — it owns its own chrome *and* its own `AgentClientProvider`, and takes `apiBaseUrl` / `agentClient` / `theme` as props so a host injects config rather than relying on build-time env vars. Avoid anything that breaks when mounted inside another app: leaking global styles, absolute route assumptions, page-level singletons.

`body` and `#root` are both flex columns (`src/index.css`) so the widget's `flex-1` has a growable parent chain to the viewport.

## Constraints

- Messages render as **plain text only — never `dangerouslySetInnerHTML`**. `normalizeInput` in `lib/utils/utils.ts` strips control characters and caps length, guarding the payload rather than the DOM.
- Conversation state is per-mount and deliberately not persisted.
- Only `VITE_*` variables reach the browser bundle. Config lives in `lib/config/`; `.env*` is gitignored apart from `.env.example`.
- Keep dependencies lean — the eventual Module Federation setup has to share them.

## Conventions inherited from the parent repo

- Branches: `feat/PLT-04-tool-wrapper-framework`, `fix/...`, `chore/...` — ticket ID in the branch.
- Every PR links its Jira ticket; CI must be green; `main` is protected.
- Ensure that the response is precise. dont add unncessary comments in the code as it cretes extra tokens. keep the code compact as mus as possible. 
