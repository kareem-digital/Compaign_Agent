/**
 * Elicitation validation and rendering. Pure: takes a row and an answer, returns
 * a verdict. Mirrors `src/lib/chat/elicitation.ts` on the client, and the two are
 * held together by the shared table in `src/test/elicitation-cases.json`.
 */

export const CODES = {
  NOT_FOUND: "elicitation_not_found",
  NOT_PENDING: "elicitation_not_pending",
  INVALID_OPTION: "invalid_option_id",
  EMPTY: "empty_answer",
  CUSTOM_NOT_ALLOWED: "custom_not_allowed",
};

const fail = (status, code, detail, extra = {}) => ({
  ok: false,
  status,
  body: { detail, code, ...extra },
});

/**
 * What the client is allowed to see. `value`, `contextLabel` and `next` are
 * server-side only — `value` is model-facing, and the other two are routing.
 */
export function publicView(row) {
  return {
    type: "options",
    id: row.id,
    prompt: row.prompt,
    select: row.select,
    allow_custom: row.allowCustom,
    custom_placeholder: row.customPlaceholder ?? null,
    status: row.status,
    options: row.options.map((option) => ({
      id: option.id,
      label: option.label,
      description: option.description ?? null,
      badge: option.badge ?? null,
    })),
    answer: row.answer,
  };
}

export function validateOptionsResponse(row, sessionId, answer) {
  // A row from another session is a 404, not a 403: never confirm that an id
  // exists somewhere the caller can't see.
  if (!row || row.sessionId !== sessionId) {
    return fail(404, CODES.NOT_FOUND, "No such elicitation for this session");
  }
  if (row.status !== "pending") {
    return fail(
      409,
      CODES.NOT_PENDING,
      `Elicitation is already ${row.status}`,
      { elicitation: publicView(row) },
    );
  }

  const ids = answer.selected_option_ids ?? [];
  if (!Array.isArray(ids)) {
    return fail(
      422,
      CODES.INVALID_OPTION,
      "selected_option_ids must be an array",
    );
  }

  const known = new Map(row.options.map((option) => [option.id, option]));
  const unknown = ids.filter((id) => !known.has(id));
  if (unknown.length) {
    return fail(422, CODES.INVALID_OPTION, "Unknown option id", {
      unknown_option_ids: unknown,
    });
  }
  if (row.select === "single" && ids.length > 1) {
    return fail(422, CODES.INVALID_OPTION, "This question takes a single choice");
  }

  const custom =
    typeof answer.custom_text === "string" ? answer.custom_text.trim() : "";
  if (custom && !row.allowCustom) {
    return fail(
      422,
      CODES.CUSTOM_NOT_ALLOWED,
      "Custom answers are not accepted here",
    );
  }
  if (ids.length === 0 && !custom) {
    return fail(422, CODES.EMPTY, "Select an option or type an answer");
  }

  // Ids resolve to model-facing values here, on the server, and only here.
  const parts = [...ids.map((id) => known.get(id).value), ...(custom ? [custom] : [])];

  return {
    ok: true,
    answer: {
      selected_option_ids: ids,
      custom_text: custom || null,
      answered_at: new Date().toISOString(),
    },
    renderedText: `${row.contextLabel ?? row.prompt}: ${parts.join(", ")}`,
  };
}

/** Turns a fixture's inline declaration into a stored row. */
export function declarationToRow(declaration, { id, sessionId }) {
  return {
    id,
    declId: declaration.id,
    sessionId,
    prompt: declaration.prompt,
    contextLabel: declaration.context_label ?? null,
    select: declaration.select,
    allowCustom: declaration.allow_custom === true,
    customPlaceholder: declaration.custom_placeholder ?? null,
    options: (declaration.options ?? []).map((option) => ({
      id: option.id,
      label: option.label,
      description: option.description ?? null,
      // Presentational only — the design's "Suggested" pill. Never routed on.
      badge: option.badge ?? null,
      value: option.value ?? option.label,
    })),
    next: declaration.next ?? null,
    // Server-owned: an author-supplied status is rejected at load time.
    status: "pending",
    answer: null,
  };
}

/** Which fixture answers this turn: by option id, then default, then nothing. */
export function resolveNextFixtureId(row, selectedOptionIds) {
  const next = row.next;
  if (!next) return null;
  if (typeof next === "string") return next;
  for (const id of selectedOptionIds) {
    if (next[id]) return next[id];
  }
  return next.default ?? null;
}
