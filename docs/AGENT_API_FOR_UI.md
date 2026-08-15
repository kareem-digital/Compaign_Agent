# Agent API — reference for the UI

The endpoints our FastAPI service exposes today, for the frontend to consume.
Not to be confused with the **VOW platform API** (`VOW_API_Integration_Reference.md`) —
that one the agent calls outbound; this one the UI calls inbound.

**Verified by running the app on 29 July 2026** (`app.__version__` 0.1.0). Every payload
below is real output, not a proposal.

---

## Basics

| | |
|---|---|
| Base URL (dev) | `http://localhost:8000` |
| Prefix | `/api/v1` — from `api_prefix` in `backend/app/config.py` |
| Content type | `application/json` |
| Interactive docs | `http://localhost:8000/docs` (disabled in production) |
| CORS | `http://localhost:3000` by default; credentials allowed |
| Auth | **none yet** — see §5 |
| Advertiser scoping | **`Vowmade-Advertiser-Id` header.** Optional in local dev (falls back to `dev_advertiser_id`), **required** in staging and production — a request without it gets `400`. Send it always |

Run it: `cd backend && uvicorn app.main:app --reload`

---

## 1. Health

Infrastructure probes. The UI does not need these, but they are useful for a
connection check in dev.

```
GET /api/v1/health/live     is the process up?
GET /api/v1/health/ready    can it serve traffic?
```

`200` — identical shape from both; `status` is `"ok"` for live, `"ready"` for ready:

```json
{ "status": "ok", "service": "vow-agent", "environment": "local", "version": "0.1.0" }
```

`/ready` does not yet check the database or VOW reachability (TODOs in `health.py`), so
today it cannot actually fail. Don't treat a ready `200` as proof the agent can work.

---

## 2. Send a chat turn

```
POST /api/v1/sessions/chat
```

**Request**

| Field | Type | Required | Notes |
|---|---|---|---|
| `message` | string | yes | 1–2000 chars. Empty or over-length → `422` |
| `session_id` | string | no | Omit to start a new conversation; send the same value to continue one. Server generates a UUID4 when omitted |

```json
{ "message": "Plan a UK CTV campaign, 50k, August", "session_id": "c0548cf4-..." }
```

**`200` response**

| Field | Type | Notes |
|---|---|---|
| `session_id` | string | Echo it back on the next turn |
| `reply` | string | Plain text. See below — one turn produces several sections |
| `stage` | string \| null | Stage the plan reached: `basics`, `inventory`, `audiences`, `forecast` |

```json
{
  "session_id": "bc7a2460-7f8b-407b-8c07-7e727fec0038",
  "stage": "forecast",
  "reply": "Here is what I understood - correct anything that is wrong before I continue.\n\n- Markets: GB\n- Flight: 2026-08-01 to 2026-08-31\n- Creative durations: 15, 30\n- Currency: GBP\n- Budget: 50000.00 GBP (GB)\n- Goal: Awareness, measured on reach (fixed for CTV)\n\nCTV inventory available in GB:\n\n- Prime Video - 18.22 CPM (15, 30s) - Amazon-owned (reach forecast available)\n- Netflix - 31.50 CPM (30s) - third-party, pre-curated (no reach forecast)\n...\n\nThree audience options - pick one and I will forecast against it.\n\n**Narrow** - In-market: premium streaming, high intent\n  6 segments, ~1,200,000 people\n  18.22 + 3.50 fee = 21.72 effective CPM\n...\n\nForecast for the Amazon portion:\n\n- Impressions: 2,472,799\n- Unique reach: 772,749 people\n- Average frequency: 3.2"
}
```

Always echo `session_id` back on the next turn — conversation state lives on the server
(LangGraph checkpointer keyed by `thread_id`), so the client does not resend history.

**One turn runs four nodes, and each one speaks.** Their messages arrive joined with blank
lines into a single `reply`, so the transport contract stays one string. Sections in order:
what was understood → CTV inventory by tier → three audience options → forecast. If you
want them as separate chat bubbles, split on `\n\n` at a heading boundary — or ask for a
`replies: string[]` field and I'll add it.

`reply` is plain text with light Markdown (`**bold**`). Render as text — never as HTML.

---

## 3. Read session state

```
GET /api/v1/sessions/{session_id}
```

**`200`**

```json
{ "session_id": "bc7a2460-...", "message_count": 5, "stage": "forecast", "next_node": null }
```

| Field | Notes |
|---|---|
| `message_count` | Total messages in the thread, **not** turns. The graph adds 5 per turn (your message + four assistant messages), so 2 turns reads as 10. Don't drive UI counters off this |
| `stage` | Last stage reached, same values as on the chat response |
| `next_node` | Array of pending node names, or `null` when the graph has run to completion. This becomes how you detect a pending approval once `interrupt()` lands — today it is always `null` |

`404` if the session has no persisted state.

---

## 4. Errors

FastAPI's default envelope throughout:

```json
{ "detail": "Session does-not-exist not found" }
```

| Status | When |
|---|---|
| `400` | No `Vowmade-Advertiser-Id` header outside local dev. Also raised if a node attempts a VOW call without advertiser context — that fails closed by design |
| `403` | A governance policy refused the action. `detail` is always the fixed string `"This action is not permitted."` — the tool, the rule and the engine's reasoning are internal and stay in the server log. **Do not offer a retry:** the answer will not change. If a user queries a refusal, take the `X-Request-ID` from the response and the exact decision can be found in the log |
| `404` | Unknown `session_id` on the GET |
| `422` | `message` empty, missing, or over 2000 chars. `detail` is an array of field errors |
| `500` | Graph execution failed. `detail` is `"Agent error"` — deliberately generic; the real cause is in the server log |
| `502` | VOW's MCP server is unreachable or returned an error after retries. Transient — worth offering a retry in the UI |

The frontend's `lib/api/http.ts` already normalises these into `ApiError`; nothing extra
is needed.

---

## 5. What is deliberately not here yet

Plan around these — they are known gaps, not oversights.

| Missing | Consequence for the UI | Lands with |
|---|---|---|
| **Auth** | No token needed, and none accepted | PLT-05 (blocked on question A1) |
| **Streaming (SSE)** | Request/response only. A turn runs four nodes and returns once at the end, so expect a few seconds of silence and keep the typing indicator | AG-UI transport (ADR-16) |
| **Artifacts** | No `{type, stage, data, layout, interaction}` envelopes. Everything arrives as prose, so the workspace zone still has nothing structured to render. `stage` is the hook it will hang off | Artifact envelope spec |
| **Approvals** | No endpoint to fetch a pending approval or submit a decision. `next_node` stays `null` | PLT-18 |
| **Audit** | No session decision history | PLT-21 |
| **Real VOW data** | The MCP client is a **mock** — canned deals, audiences and forecasts. Shapes are realistic; values are not live | real MCP server from the client |

### What the graph does today

Four of the thirteen stages in the confirmed v5 flow, wired linearly:
`extract_fields → select_inventory → suggest_audiences → predict_reach`. It reaches a
forecast-backed plan and stops there. Nothing after it exists yet, and **nothing in it
mutates anything or commits spend** — no strategy creation, no activation, no credit call.

Field extraction is deterministic heuristics, not an LLM — no LLM is wired at all yet. It
handles the common brief shapes (`UK`, `August 2026`, `£50,000`, `15 and 30 second`) and
reports what it could not find rather than guessing.

Two behaviours worth designing around, both deliberate:

- **Third-party inventory returns no reach.** For Netflix and Disney+ the forecast comes
  back `is_available: false` with impressions only, and the reply says so explicitly. Do
  not render an empty reach figure as zero — it is unavailable, which is a different thing.
- **Every turn re-runs all four nodes.** Send a correction like "make it France instead"
  and the whole chain runs again from extraction. Conversational refinement of a single
  field is not built yet.

---

## 6. Wiring the frontend

One file to implement: `frontend/src/lib/agent/http-agent-client.ts`, which currently
throws on purpose. Then set `VITE_USE_MOCK_AGENT=false` and
`VITE_API_BASE_URL=http://localhost:8000/api/v1`. Nothing above `lib/agent/` changes.

**One contract mismatch to resolve.** `AgentClient.send()` takes `{ message, history }`,
but this API is session-based and ignores history. Don't add a `history` field to the
request — hold the `session_id` in the client instance instead. One client per mount
(`AgentClientProvider`) matches the existing per-mount conversation lifetime exactly.

```ts
export function createHttpAgentClient(cfg: AppConfig): AgentClient {
  const http = createHttpClient({ baseUrl: cfg.apiBaseUrl, timeoutMs: cfg.requestTimeoutMs });
  let sessionId: string | undefined;   // server owns the transcript; we only keep the key

  return {
    async send(request, options) {
      const payload = await http.request<{
        session_id: string;
        reply: string;
        stage: string | null;
      }>("/sessions/chat", {
        method: "POST",
        headers: { "Vowmade-Advertiser-Id": cfg.advertiserId },
        body: { message: request.message, ...(sessionId ? { session_id: sessionId } : {}) },
        signal: options?.signal,
      });
      sessionId = payload.session_id;
      return { content: payload.reply };
    },
  };
}
```

`request.history` goes unused, and that is correct — server-side state is the design.

Two knock-on changes: `AppConfig` needs an `advertiserId` (thread it from the
`VowAgentWidget` prop that already exists), and the four-node chain takes a few seconds,
so `requestTimeoutMs: 30_000` is about right — don't lower it.

---

## 7. Quick check

```bash
curl http://localhost:8000/api/v1/health/live

curl -X POST http://localhost:8000/api/v1/sessions/chat \
  -H 'Content-Type: application/json' \
  -H 'Vowmade-Advertiser-Id: adv-123' \
  -d '{"message":"Plan a UK CTV campaign for August 2026, budget 50,000, 15 and 30 second creatives"}'

curl -H 'Vowmade-Advertiser-Id: adv-123' \
  http://localhost:8000/api/v1/sessions/<session_id_from_above>
```

A brief with a market, a budget, dates and a duration exercises all four nodes. Drop the
budget and you'll see the agent report what it still needs instead.

---

*Sources: `backend/app/api/health.py`, `backend/app/api/sessions.py`,
`backend/app/api/routes.py`, `backend/app/config.py`, `backend/app/agent/`. Behaviour is
pinned by `backend/tests/test_sessions_api.py`, so a contract change breaks a test rather
than only this document. Update this file whenever a router is added in `routes.py` — the
UI lane reads it as the contract.*
