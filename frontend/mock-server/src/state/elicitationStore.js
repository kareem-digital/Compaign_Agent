/**
 * Elicitation rows, keyed by the id the server issues. `status` lives here and
 * nowhere else — that is what makes it server-owned rather than something the
 * client can talk itself into.
 */
const rows = new Map();

export const elicitationStore = {
  create(row) {
    rows.set(row.id, row);
    return row;
  },
  get(id) {
    return rows.get(id);
  },
  all() {
    return [...rows.values()];
  },
  bySession(sessionId) {
    return [...rows.values()].filter((row) => row.sessionId === sessionId);
  },
  markAnswered(id, answer) {
    const row = rows.get(id);
    row.status = "answered";
    row.answer = answer;
    return row;
  },
  /** A new question closes older open ones, so only the newest is answerable. */
  supersedeOthers(sessionId, keepId) {
    const closed = [];
    for (const row of rows.values()) {
      if (row.sessionId === sessionId && row.id !== keepId && row.status === "pending") {
        row.status = "superseded";
        closed.push(row);
      }
    }
    return closed;
  },
  clear() {
    rows.clear();
  },
};
