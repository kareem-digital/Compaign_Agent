# VOW Agent Frontend

React 18 + Vite SPA for the VOW Agent chat experience. Runs standalone today and
is structured to be exposed as a Module Federation remote later, without a
refactor.

Stack: React 18.2, Vite 6, TypeScript (strict), Tailwind CSS v4, daisyUI v5,
Vitest + React Testing Library.

## Running locally

```bash
npm install
cp .env.example .env    # optional; the defaults below apply without it
npm run mock:dev        # terminal 1: fixture-driven chat API on :4100
npm run dev             # terminal 2: http://localhost:3000
```

There is no in-process mock transport — `VITE_API_BASE_URL` defaults to
`mock-server/`, so it needs to be running for the app to be functional without
a real backend.

| Script                   | What it does                                              |
| ------------------------ | ---------------------------------------------------------- |
| `npm run dev`            | Standalone dev server on port 3000                        |
| `npm run dev:remote`     | Serves the widget as a Module Federation remote on port 3001 |
| `npm run build`          | Typecheck + production build to `dist/agent`               |
| `npm run build:remote`   | Builds the MF remote to `dist/mfe`                         |
| `npm run build:all`      | Both builds                                                |
| `npm run preview`        | Serve the production standalone build                      |
| `npm run preview:remote` | Serve the production remote build                          |
| `npm run mock:dev`       | Fixture-driven mock chat API on `:4100` (`mock-server/`)   |
| `npm test`               | Vitest suite (single run)                                  |
| `npm run test:watch`     | Vitest in watch mode                                       |
| `npm run test:coverage`  | Vitest + v8 coverage; enforces the thresholds CI gates on  |
| `npm run typecheck`      | `tsc -b --noEmit`                                          |
| `npm run lint`           | ESLint                                                      |
| `npm run docker:build`   | Builds the production Docker image                         |
| `npm run docker:run`     | Runs the built image locally                                |

See `/docs` (`architecture.md`, `ui.md`, `structure.md`) for styling, i18n,
responsiveness and folder-structure conventions — read before writing code
that touches any of those.

## Architecture

```
src/
├── components/chat/    ChatContainer, ChatInput, MessageBubble, MessageList,
│                       TypingIndicator, WelcomeScreen
├── components/layout/  Header
├── hooks/use-chat.ts   Local conversation state (not persisted)
├── lib/api/            http.ts transport + ApiError — the only place fetch is called
├── lib/agent/          AgentClient contract, http implementation, factory, provider
├── lib/config/         Runtime config from VITE_* env vars
├── lib/utils/          cn, createId, normalizeInput, formatTime
├── types/chat.ts       ChatMessage, MessageRole, ChatStatus
└── widget/             VowAgentWidget — the embeddable surface
```

### The API layer

Everything that reaches the backend goes through one boundary, so the transport
stays swappable:

```
components → use-chat → useAgentClient() → AgentClient → http-agent-client → http.ts
                          (context)         (contract)                       (transport)
```

- **`lib/api/http.ts`** owns base-URL resolution, JSON handling, per-request
  timeouts, the `X-Request-ID` correlation header, and normalizing every
  failure into a typed `ApiError`. Caller aborts pass through untouched,
  because cancellation is control flow rather than an error.
- **`lib/agent/types.ts`** defines `AgentClient` — the contract the UI depends
  on. It does not change when the backend arrives.
- **`createAgentClient(config)`** builds the `AgentClient` from config — always
  the HTTP implementation, there is no in-process mock — and
  `AgentClientProvider` supplies it through context. There is deliberately no
  exported `agentClient` singleton: a singleton would fix the choice at import
  time, which is what made the previous Next.js app's transport impossible to
  stub or inject.

### Swapping mock-server for the real backend

`createHttpAgentClient` (`src/lib/agent/http-agent-client.ts`) is the only
`AgentClient` implementation, already built against the `POST /sessions/chat`
contract. The real backend still registers only `/health` (`app/api/routes.py`)
— sessions and approvals are TODO — so `VITE_API_BASE_URL` defaults to
`mock-server/`, which speaks the identical wire format on its own port. Once
the real backend's sessions router lands, point at it in `frontend/.env.local`:

```
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

`npm run mock:dev` starts the mock server — see `mock-server/README.md`.
Nothing above `lib/agent/` changes either way.

## Environment variables

| Variable            | Default                        | Purpose                            |
| -------------------- | ------------------------------- | ----------------------------------- |
| `VITE_API_BASE_URL` | `http://localhost:4100/api/v1` | Backend base URL (mock-server or the real backend) |

Only `VITE_*` variables reach the browser bundle. Never put secrets here.

## Embedding

`VowAgentWidget` is the self-contained mount point — it owns its own chrome and
its own transport, and makes no route or page-level assumptions. A host can
inject configuration through props rather than environment variables, so one
bundle serves many environments:

```tsx
<VowAgentWidget
  apiBaseUrl="https://api.example.com/api/v1"
  theme="dark"
  // or hand it a transport outright:
  // agentClient={myClient}
/>
```

Module Federation is fully configured (`vite.config.ts`): `npm run build:remote`
outputs `dist/mfe`, exposing `./VowAgentWidget` from `src/widget/federated.tsx`
for a host to consume as a remote.

## Notes

- Deferred work: MSW, Sentry, and Playwright E2E (see `tests/README.md`).
- Messages render as plain text — never `dangerouslySetInnerHTML`.
