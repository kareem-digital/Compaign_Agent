# Interactive options (elicitation) contract

How the agent asks a structured question mid-conversation and how the client answers it.
This is the contract the frontend implements today, and the reference for the backend
implementation. A runnable version lives in `mock-server/` (`npm run mock:dev`).

There is **no separate answer endpoint**. Answers go back through `POST /sessions/chat`
like any other turn.

---

## Request — `POST /api/v1/sessions/chat`

A typed turn:

```json
{
  "session_id": "sess_01H8W",
  "client_message_id": "b3f1a0c2-…",
  "message": "Plan a CTV campaign for Q4",
  "content": [{ "type": "text", "text": "Plan a CTV campaign for Q4" }]
}
```

Answering a question — same endpoint, same envelope:

```json
{
  "session_id": "sess_01H8W",
  "client_message_id": "9d21e4f7-…",
  "content": [
    {
      "type": "options_response",
      "elicitation_id": "elc_01H8Y",
      "selected_option_ids": ["opt_2"],
      "custom_text": null
    }
  ]
}
```

A typed answer is the same shape with an empty selection — no special case:

```json
{
  "type": "options_response",
  "elicitation_id": "elc_01H8Y",
  "selected_option_ids": [],
  "custom_text": "I'm flexible, depends on the dates"
}
```

| Field | Notes |
|---|---|
| `client_message_id` | **Required.** Idempotency key, scoped to the session. See below. |
| `session_id` | Omitted on the first turn; the server issues one and the client echoes it thereafter. |
| `content` | At least one `text` or `options_response` block. At most **one** `options_response` per turn. |
| `message` | Legacy plain-text projection of the `text` blocks, so today's backend keeps working. **Omitted on answer-only turns** — see below. |

**Why `message` is absent when answering.** The client submits option **ids**, never label
text. Putting labels into a field that becomes prompt context would let the client decide
what the model reads. The 2000-character cap therefore applies to text only; an answer-only
turn carries no text and must not be rejected for that.

## Response — `200`

```json
{
  "session_id": "sess_01H8W",
  "stage": "basics",
  "reply": "Creative length drives both the CPM and the inventory you can buy.",
  "message": {
    "id": "msg_01H8X",
    "role": "assistant",
    "content": [
      { "type": "text", "text": "Creative length drives both the CPM and the inventory you can buy." },
      {
        "type": "options",
        "id": "elc_01H8Y",
        "prompt": "How long is the creative?",
        "select": "single",
        "allow_custom": true,
        "custom_placeholder": "Answer in your own words…",
        "status": "pending",
        "options": [
          {
            "id": "opt_10s",
            "label": "10 seconds",
            "description": "Cheapest CPM — most impressions for the budget",
            "badge": "Suggested"
          },
          { "id": "opt_15s", "label": "15 seconds", "description": null, "badge": null }
        ],
        "answer": null
      }
    ]
  },
  "resolved_elicitations": []
}
```

`reply` is a legacy mirror, derived by joining the `text` blocks. It exists so the current
backend and every existing fixture keep working unchanged. An options block contributes
nothing to it. A block-aware client ignores `reply`; a legacy client ignores `message`.

`select` is `"single"` or `"multi"` — the only difference between a radio-style question and
a checklist, and the one field the UI keys its whole interaction model off.

### `value` is not on the wire

Each option carries `id`, `label`, optional `description` and optional `badge` — and no
`value`. The model-facing string stays server-side: the server resolves ids to values and
renders them into model context as plain text (`Creative length: 10 seconds`).

The client renders `label` and submits `id`, so it cannot leak or tamper with prompt
payload, and nobody can POST arbitrary text as a "selection". The frontend mapper copies
option fields one at a time rather than spreading, so a server that sends `value` anyway
has it dropped at the boundary (`src/lib/agent/http-agent-client.ts`).

`badge` is a short presentational tag drawn as a pill on the option row — "Suggested",
"Ran last year". It is the server's wording, never routed on and never submitted back.

### `resolved_elicitations`

Elicitations whose status changed this turn: the one just answered, plus any older open
rows the new question superseded.

**This is load-bearing, not cosmetic.** The answered question lives in an *earlier*
message. Without this field the client would have to mark it answered itself — and an
answer that produces no follow-up question would leave the last options block `pending`
and still tappable.

```json
"resolved_elicitations": [
  {
    "type": "options",
    "id": "elc_01H8Y",
    "status": "answered",
    "answer": {
      "selected_option_ids": ["opt_10s"],
      "custom_text": null,
      "answered_at": "2026-08-07T19:00:55.511Z"
    },
    "…": "the rest of the block, unchanged"
  }
]
```

It also covers the case where the user ignores the question and types instead: the server
reports the row as `superseded` and the client closes the card.

## Status — server-owned

| status | answerable | meaning |
|---|---|---|
| `pending` | yes, **if it is the newest options block** | open question |
| `answered` | no | resolved; `answer` echoes what was recorded |
| `superseded` | no | the agent moved on and asked something else |
| `expired` | no | closed before it was answered |

The client **renders** status and never derives it. An unrecognised value narrows to
`expired` — fail closed, so an unknown status can never make a dead row tappable.

Two independent rules decide whether a question is answerable, and both must hold:

1. **`status === "pending"`** — the server's call, always.
2. **It is the newest options block in the transcript** — a pure presentation rule over
   what the server sent. Scroll up and every earlier question is read-only, or users tap a
   question from twelve turns ago and the conversation stops making sense.

What is *banned* is inferring answeredness from "the user tapped it" or "a newer message
exists". On reload the client rehydrates status from the server; a refresh must never
re-open something already answered.

## Errors

| status | code | when |
|---|---|---|
| `409` | `elicitation_not_pending` | The row exists but isn't pending. **Body carries the full current `elicitation`.** |
| `404` | `elicitation_not_found` | Unknown id, **or an id belonging to another session** — never confirm cross-session existence. |
| `422` | `invalid_option_id` | An option id isn't real, or two ids on a `single` question. Includes `unknown_option_ids`. |
| `422` | `empty_answer` | No selection and no custom text (whitespace doesn't count). |
| `422` | `custom_not_allowed` | Custom text against `allow_custom: false`. |
| `422` | `multiple_answers` / `empty_content` | Malformed `content`. |

```json
{
  "detail": "Elicitation is already answered",
  "code": "elicitation_not_pending",
  "elicitation": { "type": "options", "id": "elc_01H8Y", "status": "answered", "answer": { "…": "…" } }
}
```

The 409 body is what lets a stale tab correct itself instead of silently double-answering.
The client patches the block in place with the server's version. If the recorded answer
matches what it just submitted, that was its own double-submit landing twice and is
reconciled with no error shown; otherwise it drops its optimistic bubble and explains.

## Idempotency

`client_message_id` is scoped to the session. Users double-tap buttons constantly.

- A repeat of a key that produced a **2xx** replays that response byte-for-byte. It does
  **not** 409.
- **409 is reserved for a different key hitting a non-pending row** — a genuinely stale
  tab. That distinction is the whole point: one is a fumbled button, the other is a
  conflict the user needs to know about.
- **4xx responses are not recorded.** A client that got a 422, fixed its payload and
  retried with the same key must not be stuck replaying its own mistake.
- A retry after a network failure reuses the original key, so the server replays rather
  than recording the same answer twice.

## Interaction rules the client implements

Design reference: slide **13a** of the *VOW Agent Start* Claude Design project.

- **Both modes stage a draft and send on an explicit Confirm.** Tapping a row selects it and
  posts nothing, so a mis-tap is free to correct and no turn reaches the agent by accident.
  `select: "single"` draws numbered tokens and replaces the selection; `select: "multi"`
  draws checkboxes and toggles, with the count on the button.
- The number keys `1`–`9` select a row, matching the design's *"press 1–4"* hint. They
  select rather than submit, for the same reason. The shortcut is bound only for the one
  answerable card and ignores keystrokes aimed at a field, so neither text input is
  hijacked.
- `allow_custom` gives the user **two ways to type an answer, and both send the same
  request**: the field on the card itself, and the main composer, whose placeholder becomes
  *"Answer in your own words…"* while the question is open. Either one posts an
  `options_response` with `selected_option_ids: []` and `custom_text`, so a typed answer is
  never a loose turn the server has to guess about. With `allow_custom: false`, composer
  text is an ordinary turn and the server reports the row `superseded`.
- An in-flight tap disables the controls but is tracked separately from `status`, so a
  spinner never implies a lock and a lock never implies a spinner.

## Backend gaps

Relative to the endpoint that exists today (`backend/app/api/sessions.py`):

1. `stage` is not returned — the frontend wire type and the mock server manufacture it.
2. No `message.content` blocks, no elicitation rows, no server-owned `status`, no `answer`
   echo, no `resolved_elicitations`.
3. No `client_message_id` idempotency, no 409-with-current-state.
4. `message` is currently required at 1..2000 characters, which blocks answer-only turns.
5. **No session history endpoint**, so "rehydrate status on reload" cannot be satisfied
   yet. Shape designed, not implemented:

   ```
   GET /api/v1/sessions/{session_id}/messages
   → { session_id, stage, messages: [ { id, role, created_at, client_message_id?, content: [...] } ] }
   ```

   The client side is an **optional** `AgentClient.loadHistory?()`
   (`src/lib/agent/types.ts`), declared but with no implementer and no caller yet, so
   neither existing client has to provide it on day one. When it lands, note that it
   contradicts CLAUDE.md's "conversation state is per-mount and deliberately not
   persisted" — that line needs an explicit amendment, not a quiet override.

## Where this lives in the frontend

| Concern | File |
|---|---|
| Domain types (camelCase) | `src/types/chat.ts` |
| Wire types (snake_case, type-only) | `src/lib/agent/wire.ts` |
| Wire ↔ domain mapping, 409 translation | `src/lib/agent/http-agent-client.ts` |
| Typed conflict error | `src/lib/agent/errors.ts` |
| Selectors and client-side validation | `src/lib/chat/elicitation.ts` |
| Answer flow, reconciliation, idempotency | `src/hooks/use-chat.ts` |
| Rendering | `src/components/chat/OptionsBlockCard.tsx` |
| Composer routing while a question is open | `src/components/chat/ChatWorkspace.tsx` |
| HTTP reference implementation | `mock-server/src/domain/` |

`wire.ts` is imported by `http-agent-client.ts` alone and is not re-exported from the
`lib/agent` barrel, so "the wire format is the transport's business" is enforced by the
import graph rather than by convention.
