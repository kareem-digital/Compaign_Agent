import { randomUUID } from "node:crypto";

import { normalizeOutbound, parseInbound } from "./blocks.js";
import {
  declarationToRow,
  publicView,
  resolveNextFixtureId,
  validateOptionsResponse,
} from "./elicitation.js";
import { matchFixture } from "../fixtures/matcher.js";

/** Next step of an in-flight sequence, advancing (or retiring) the session. */
function nextSequenceStep(sessionId, entry, sequenceStore) {
  const { fixture } = entry;
  const step = fixture.sequence[entry.index];
  entry.index += 1;

  if (entry.index >= fixture.sequence.length) {
    if (fixture.repeatLast) {
      entry.index = fixture.sequence.length - 1;
    } else {
      sequenceStore.delete(sessionId);
    }
  }
  return step;
}

/** A text turn picks its fixture the way it always has. */
function resolveTextTurn(text, fixtures, sessionId, sequenceStore) {
  // An active sequence owns the conversation: the message text is ignored
  // until the script runs out, so a scripted flow can't be derailed midway.
  const active = sequenceStore.get(sessionId);
  if (active) return nextSequenceStep(sessionId, active, sequenceStore);

  const fixture = matchFixture(text, fixtures);
  if (fixture.sequence) {
    sequenceStore.set(sessionId, { fixture, index: 1 });
    return fixture.sequence[0];
  }
  return fixture;
}

const defaultFixture = (fixtures) =>
  fixtures.find((f) => f.match.type === "default");

/**
 * The follow-up after an answer. Deliberately never text-matches: the rendered
 * answer "Budget: under $1k" contains "budget", so `matchFixture` would loop
 * straight back to the question that asked it. Routing as a side effect of
 * rendering is a nasty class of bug, so an answer routes only through a
 * sequence, then the declaration's `next`, then the default fixture.
 */
function resolveAnswerTurn(row, check, fixtures, sessionId, sequenceStore) {
  const active = sequenceStore.get(sessionId);
  if (active) return nextSequenceStep(sessionId, active, sequenceStore);

  const nextId = resolveNextFixtureId(row, check.answer.selected_option_ids);
  if (!nextId) return defaultFixture(fixtures);

  const fixture = fixtures.find((f) => f.id === nextId);
  if (!fixture) {
    console.warn(
      `[mock-server] elicitation ${row.declId} points at unknown fixture "${nextId}"`,
    );
    return defaultFixture(fixtures);
  }
  if (fixture.sequence) {
    sequenceStore.set(sessionId, { fixture, index: 1 });
    return fixture.sequence[0];
  }
  return fixture;
}

/**
 * Registers any elicitation a reply declares, rewriting the block in place with
 * the id the server issued and stripping the server-only routing fields. The
 * fixture author therefore writes the options exactly once.
 */
function registerDeclarations(payload, sessionId, elicitationStore, newId) {
  const closed = [];
  for (const [index, block] of payload.message.content.entries()) {
    if (block.type !== "options") continue;

    const id = newId(block.id);
    const row = elicitationStore.create(
      declarationToRow(block, { id, sessionId }),
    );
    closed.push(...elicitationStore.supersedeOthers(sessionId, id));
    payload.message.content[index] = publicView(row);
  }
  return closed;
}

/**
 * One chat turn, start to finish, with no express in sight. Returns what the
 * route should send.
 */
export function handleTurn({ body, fixtures, stores, ids = {} }) {
  const { elicitationStore, idempotencyStore, sequenceStore } = stores;
  const newSessionId = ids.sessionId ?? randomUUID;
  const newMessageId = ids.messageId ?? (() => `msg_${randomUUID()}`);
  const newElicitationId =
    ids.elicitationId ??
    ((declId) => `${declId}.${randomUUID().slice(0, 8)}`);

  const parsed = parseInbound(body);
  if (!parsed.ok) {
    return {
      status: parsed.error.status,
      payload: parsed.error.body,
      log: "invalid request",
    };
  }

  const { text, optionsResponse, sessionId: incoming, clientMessageId } =
    parsed.value;
  const sessionId = incoming || newSessionId();

  // Replay before touching any state. A double-tap therefore never sees a 409;
  // only a *different* key against a closed row does, and that distinction is
  // the whole point — one is a fumbled button, the other is a stale tab.
  if (clientMessageId) {
    const replay = idempotencyStore.get(sessionId, clientMessageId);
    if (replay) {
      return { ...replay, log: `replay ${clientMessageId}` };
    }
  }

  let step;
  const vars = {};
  let resolved = [];

  if (optionsResponse) {
    const row = elicitationStore.get(optionsResponse.elicitation_id);
    const check = validateOptionsResponse(row, sessionId, optionsResponse);
    if (!check.ok) {
      return { status: check.status, payload: check.body, log: check.body.code };
    }

    elicitationStore.markAnswered(row.id, check.answer);
    resolved.push(row);
    vars.answer = check.renderedText;
    step = resolveAnswerTurn(row, check, fixtures, sessionId, sequenceStore);
  } else {
    step = resolveTextTurn(text, fixtures, sessionId, sequenceStore);
  }

  const { status = 200, body: fixtureBody } = step.response;
  if (status >= 300) {
    return {
      status,
      payload: fixtureBody,
      delayMs: step.delayMs,
      log: `fixture ${step.id ?? "step"} -> ${status}`,
    };
  }

  const payload = {
    session_id: sessionId,
    ...normalizeOutbound(fixtureBody, { vars, messageId: newMessageId() }),
  };
  resolved.push(
    ...registerDeclarations(
      payload,
      sessionId,
      elicitationStore,
      newElicitationId,
    ),
  );
  payload.resolved_elicitations = resolved.map(publicView);

  // Only 2xx is replayable: a client that got a 422, fixed its payload and
  // retried with the same key must not be stuck replaying its own mistake.
  if (clientMessageId) {
    idempotencyStore.set(sessionId, clientMessageId, { status, payload });
  }

  return { status, payload, delayMs: step.delayMs, log: `session=${sessionId}` };
}
