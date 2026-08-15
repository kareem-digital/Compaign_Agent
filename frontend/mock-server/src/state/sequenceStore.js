/**
 * Tracks how far each session has advanced through a `sequence` fixture.
 * In-memory and per-process: restarting the server resets every conversation,
 * which is the intended behaviour for a dev fixture server.
 */
const sessions = new Map();

export const sequenceStore = {
  get: (sessionId) => sessions.get(sessionId),
  set: (sessionId, entry) => sessions.set(sessionId, entry),
  delete: (sessionId) => sessions.delete(sessionId),
  clear: () => sessions.clear(),
};
