/**
 * Replayable responses, keyed by session + client_message_id. Bounded FIFO so a
 * long-running dev session can't leak.
 */
const MAX_ENTRIES = 500;
const seen = new Map();

const keyFor = (sessionId, clientMessageId) =>
  `${sessionId}:${clientMessageId}`;

export const idempotencyStore = {
  get(sessionId, clientMessageId) {
    return seen.get(keyFor(sessionId, clientMessageId));
  },
  set(sessionId, clientMessageId, record) {
    seen.set(keyFor(sessionId, clientMessageId), record);
    if (seen.size > MAX_ENTRIES) seen.delete(seen.keys().next().value);
  },
  clear() {
    seen.clear();
  },
};
