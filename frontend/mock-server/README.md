# Mock chat server

A fixture-driven stand-in for the FastAPI chat backend, so frontend work isn't
blocked while the real backend is still changing. It speaks the same wire
contract as `backend/app/api/sessions.py`, so the widget can be pointed at it by
changing two env vars and nothing else.

**What this is not:** it isn't MSW, which intercepts calls inside the app. This
is a real HTTP server on a real port, so it also works with curl, Postman, and
anything else that speaks HTTP. It is a local dev tool and is never deployed.

## Running it

```bash
cd frontend/mock-server
npm install
npm run dev          # nodemon, restarts when src/ or fixtures/ change
```

Or from `frontend/`: `npm run mock:dev`.

Listens on `http://localhost:4100/api/v1` (override with `PORT`). The real
backend owns 8000, so both can run at once.

## Pointing the frontend at it

`VITE_API_BASE_URL` defaults to `http://localhost:4100/api/v1`, so `npm run dev`
already points here — just have `npm run mock:dev` running alongside it. To
point at the real backend instead, set in `frontend/.env.local`:

```
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

## Endpoints

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/sessions/chat` | The fixture-driven chat endpoint |
| GET | `/api/v1/health/live` | Parity with the real backend |
| GET | `/api/v1/health/ready` | Parity with the real backend |
| GET | `/api/v1/_dev/elicitations` | **Dev only.** Lists the rows this process holds |
| POST | `/api/v1/_dev/elicitations/:id/expire` | **Dev only.** Closes a question behind the UI's back |

`POST /sessions/chat` speaks two dialects and always answers in both.

The legacy one still works exactly as before: send `{ message, session_id? }`, get
`{ session_id, reply, stage }` back. `message` must be 1–2000 characters or you get
a `422`.

The block dialect adds `content` (and `client_message_id`), and the response adds
`message.content` plus `resolved_elicitations` alongside the flat `reply`. That is
what carries interactive questions — see `docs/elicitation.md` for the full
contract, the error codes and the idempotency rules.

Omit `session_id` to start a new conversation; send back the one you were given to
continue it. Elicitation rows, their server-owned `status` and the idempotency
records all live in memory, so restarting the server resets everything.

The two `_dev` routes exist so the `409 elicitation_not_pending` path is curl-able
without opening a second tab: list the rows, expire one, then answer it from the UI.

## Writing fixtures

One JSON file per scenario in `fixtures/chat/`. Add a file, save it, and nodemon
picks it up — no code changes, no restart.

```jsonc
{
  "id": "budget-question",          // required, unique-ish label for logs
  "description": "...",             // optional, for whoever reads the file next
  "priority": 10,                   // optional, default 0. Higher wins.
  "match": { "value": "budget" },   // see below
  "delayMs": 400,                   // optional simulated latency
  "response": {
    "status": 200,
    "body": { "reply": "...", "stage": "basics" }
  }
}
```

Never write `session_id` into a fixture — the server fills it in.

### Matching

`match.type` is one of:

| type | behaviour |
|---|---|
| `contains` | **default.** True if the message contains `value` |
| `exact` | True if the trimmed message equals `value` |
| `regex` | True if `value` (a JS regex) matches the message |
| `default` | The fallback. Exactly one fixture must use this |
| `none` | Never matches text. Reachable only via an elicitation's `next` |

Matching ignores case unless you set `"caseSensitive": true`.

Fixtures are tried in descending `priority`, then alphabetically by filename,
and the first match wins. If nothing matches, the `default` fixture answers. If
a fixture file is malformed the server logs a warning and skips it rather than
refusing to start — but it *will* refuse to start if no `default` fixture exists
or if two of them do.

### Simulating errors

Set a non-2xx `status`. The body is returned untouched, so use FastAPI's shape:

```jsonc
{
  "id": "error-rate-limit",
  "priority": 100,
  "match": { "value": "simulate rate limit" },
  "response": {
    "status": 429,
    "body": { "detail": "Rate limit exceeded (simulated by mock-server)" }
  }
}
```

Give error fixtures a high priority so their trigger phrase isn't swallowed by a
broader `contains` fixture.

### Scripting a multi-turn conversation

Use `sequence` instead of `response` to play replies out across successive
turns. Once triggered, the sequence owns that `session_id` and later messages
advance the script regardless of what is typed — so a scripted demo can't be
derailed halfway through.

```jsonc
{
  "id": "onboarding-sequence",
  "match": { "value": "start onboarding" },
  "repeatLast": true,
  "sequence": [
    { "response": { "status": 200, "body": { "reply": "Which market?", "stage": "basics" } } },
    { "delayMs": 700, "response": { "status": 200, "body": { "reply": "Which audiences?", "stage": "audiences" } } }
  ]
}
```

`repeatLast: true` holds on the final reply forever. Without it the script is
retired when it runs out and later messages match normally again. Sequence
progress lives in memory, so restarting the server resets every conversation.

`delayMs` goes on each step for sequences, and at the top level for single
responses.

### Asking an interactive question

Write `content` instead of `reply` and include an `options` block. The flat `reply`
mirror is derived from the text blocks for you, so you author the reply once.

```jsonc
{
  "id": "creative-length-elicitation",
  "priority": 20,
  "match": { "type": "regex", "value": "\\b(creative|length)\\b" },
  "response": {
    "status": 200,
    "body": {
      "stage": "basics",
      "content": [
        { "type": "text", "text": "Creative length drives the CPM." },
        {
          "type": "options",
          "id": "elc_creative_length",   // your label; the server issues the real id
          "prompt": "How long is the creative?",
          "context_label": "Creative length",     // server-side: prefixes the rendered answer
          "select": "single",                     // or "multi"
          "allow_custom": true,
          "custom_placeholder": "Answer in your own words…",
          "options": [
            {
              "id": "opt_10s",
              "label": "10 seconds",              // the only option text the client sees
              "description": "Cheapest CPM",
              "badge": "Suggested",               // presentational pill
              "value": "10 seconds"               // server-side: what the model reads
            }
          ],
          "next": "creative-length-followup"      // or { "opt_10s": "…", "default": "…" }
        }
      ]
    }
  }
}
```

Three fields never reach the client: `value`, `context_label` and `next`. `value` is
model-facing — keeping it server-side is what stops a client deciding what the model
reads — and the other two are routing. `status` is server-owned; authoring it is a
load-time error.

When the answer lands, the server records it, marks any older open question
`superseded`, renders `"{context_label}: {value}"`, and routes to the fixture named
by `next` — resolving by selected option id first, then `next.default`, then the
`default` fixture. That rendered string is available to the follow-up fixture as
`{{answer}}`:

```jsonc
{
  "id": "creative-length-followup",
  "match": { "type": "none" },
  "response": { "status": 200, "body": { "reply": "Saved — {{answer}}." } }
}
```

An answer turn deliberately **never** text-matches a fixture. The rendered answer
"Budget: under $1k" contains "budget", so matching would loop straight back to the
question that asked it. Routing as a side effect of rendering is a nasty class of
bug, so an answer routes only through a sequence, then `next`, then the default.

Give follow-ups `match.type: "none"` unless you also want them reachable by typing.
