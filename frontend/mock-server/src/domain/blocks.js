/**
 * Request parsing and response shaping. Pure, and imports nothing outside
 * `node:*` — mock-server's own dependencies are never installed in CI, so the
 * logic worth testing has to be reachable without express.
 */

export const MAX_MESSAGE_LENGTH = 2000;

const invalid = (detail, code) => ({
  ok: false,
  error: { status: 422, body: code ? { detail, code } : { detail } },
});

/**
 * Accepts both dialects. The legacy `{message}` path keeps its exact rules and
 * its exact 422 string, so every existing fixture and client behaves as before.
 */
export function parseInbound(body) {
  const {
    message,
    content,
    session_id: sessionId,
    client_message_id: clientMessageId,
  } = body ?? {};
  const lengthError = `message must be 1-${MAX_MESSAGE_LENGTH} characters`;

  if (!Array.isArray(content)) {
    if (
      typeof message !== "string" ||
      message.trim().length === 0 ||
      message.length > MAX_MESSAGE_LENGTH
    ) {
      return invalid(lengthError);
    }
    return {
      ok: true,
      value: { text: message, optionsResponse: null, sessionId, clientMessageId },
    };
  }

  const text = content
    .filter((block) => block?.type === "text")
    .map((block) => block.text ?? "")
    .join("\n")
    .trim();
  const answers = content.filter((block) => block?.type === "options_response");

  if (answers.length > 1) {
    return invalid(
      "at most one options_response block per turn",
      "multiple_answers",
    );
  }
  if (!text && answers.length === 0) {
    return invalid(
      "content must contain a text or options_response block",
      "empty_content",
    );
  }
  // The length rule covers text only: an answer-only turn carries none, and
  // must not be rejected for that.
  if (text.length > MAX_MESSAGE_LENGTH) return invalid(lengthError);

  return {
    ok: true,
    value: {
      text,
      optionsResponse: answers[0] ?? null,
      sessionId,
      clientMessageId,
    },
  };
}

export function interpolate(value, vars) {
  return String(value).replace(/\{\{(\w+)\}\}/g, (whole, name) =>
    name in vars ? vars[name] : whole,
  );
}

/**
 * Emits both dialects on every success: blocks under `message` for a
 * block-aware client, and a flat `reply` string for the backend contract that
 * exists today. A fixture authors `content` or `reply` and gets the other free.
 */
export function normalizeOutbound(fixtureBody, { vars = {}, messageId } = {}) {
  const { content, reply, ...rest } = fixtureBody;

  const blocks = Array.isArray(content)
    ? content.map((block) =>
        block.type === "text"
          ? { ...block, text: interpolate(block.text, vars) }
          : block,
      )
    : typeof reply === "string"
      ? [{ type: "text", text: interpolate(reply, vars) }]
      : [];

  const mirror = blocks
    .filter((block) => block.type === "text")
    .map((block) => block.text)
    .join("\n\n");

  return {
    stage: null,
    ...rest,
    reply: mirror,
    message: { id: messageId, role: "assistant", content: blocks },
  };
}
