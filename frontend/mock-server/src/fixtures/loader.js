import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

// "none" never matches text: the fixture is reachable only via an elicitation's
// `next`, so it can't be triggered accidentally by a passing mention.
const MATCH_TYPES = new Set(["contains", "exact", "regex", "default", "none"]);
const VALUE_OPTIONAL = new Set(["default", "none"]);
const SELECT_TYPES = new Set(["single", "multi"]);

/** An inline elicitation declaration inside a fixture's response body. */
function validateOptionsBlock(block, where, errors) {
  if (typeof block.id !== "string" || !block.id.trim()) {
    errors.push(`${where}: options block needs a non-empty \`id\``);
  }
  if (typeof block.prompt !== "string" || !block.prompt.trim()) {
    errors.push(`${where}: options block needs a \`prompt\``);
  }
  if (!SELECT_TYPES.has(block.select)) {
    errors.push(`${where}: \`select\` must be "single" or "multi"`);
  }
  if (!Array.isArray(block.options) || block.options.length === 0) {
    errors.push(`${where}: options block needs at least one option`);
    return;
  }
  const ids = block.options.map((option) => option?.id);
  if (ids.some((id) => typeof id !== "string" || !id.trim())) {
    errors.push(`${where}: every option needs a non-empty \`id\``);
  }
  if (new Set(ids).size !== ids.length) {
    errors.push(`${where}: option ids must be unique`);
  }
  if (block.options.some((option) => typeof option?.label !== "string")) {
    errors.push(`${where}: every option needs a \`label\``);
  }
  // Server-owned. Letting a fixture set it would make "the client never infers
  // status" true of the client and false of the fixtures.
  if ("status" in block) {
    errors.push(`${where}: \`status\` is server-owned and must not be authored`);
  }
}

function validateResponseBody(body, where, errors) {
  if (!body) {
    errors.push(`${where} is missing response.body`);
    return;
  }
  if (!Array.isArray(body.content)) return;

  const optionBlocks = body.content.filter((block) => block?.type === "options");
  if (optionBlocks.length > 1) {
    errors.push(`${where}: at most one options block per response`);
  }
  optionBlocks.forEach((block) => validateOptionsBlock(block, where, errors));
}

function validate(fixture, file) {
  const errors = [];

  if (typeof fixture.id !== "string" || !fixture.id.trim()) {
    errors.push("`id` must be a non-empty string");
  }
  if (!fixture.match || typeof fixture.match !== "object") {
    errors.push("`match` is required");
  } else {
    const type = fixture.match.type ?? "contains";
    if (!MATCH_TYPES.has(type)) {
      errors.push(`unknown match.type "${type}" (expected ${[...MATCH_TYPES].join(", ")})`);
    }
    if (!VALUE_OPTIONAL.has(type) && typeof fixture.match.value !== "string") {
      errors.push(
        '`match.value` must be a string unless match.type is "default" or "none"',
      );
    }
    if (type === "regex") {
      try {
        new RegExp(fixture.match.value);
      } catch (cause) {
        errors.push(`match.value is not a valid regex: ${cause.message}`);
      }
    }
  }

  const hasResponse = fixture.response !== undefined;
  const hasSequence = fixture.sequence !== undefined;
  if (hasResponse === hasSequence) {
    errors.push("exactly one of `response` or `sequence` is required");
  }
  if (hasSequence && (!Array.isArray(fixture.sequence) || fixture.sequence.length === 0)) {
    errors.push("`sequence` must be a non-empty array");
  }
  if (hasSequence && Array.isArray(fixture.sequence)) {
    fixture.sequence.forEach((step, i) =>
      validateResponseBody(step?.response?.body, `sequence[${i}]`, errors),
    );
  }
  if (hasResponse) {
    validateResponseBody(fixture.response.body, "`response.body`", errors);
  }

  if (errors.length > 0) {
    console.warn(`[mock-server] skipping ${file}:\n  - ${errors.join("\n  - ")}`);
    return false;
  }
  return true;
}

/**
 * Reads every fixture in `dir` at startup. A malformed file is skipped with a
 * warning rather than taking the server down — one author's typo shouldn't
 * block everyone else's dev environment.
 */
export function loadFixtures(dir) {
  const files = readdirSync(dir)
    .filter((f) => f.endsWith(".json"))
    .sort();

  const fixtures = [];
  for (const file of files) {
    let parsed;
    try {
      parsed = JSON.parse(readFileSync(join(dir, file), "utf8"));
    } catch (cause) {
      console.warn(`[mock-server] skipping ${file}: invalid JSON — ${cause.message}`);
      continue;
    }
    if (validate(parsed, file)) {
      fixtures.push({ ...parsed, file });
    }
  }

  const defaults = fixtures.filter((f) => f.match.type === "default");
  if (defaults.length > 1) {
    throw new Error(
      `[mock-server] found ${defaults.length} fallback fixtures (${defaults
        .map((f) => f.file)
        .join(", ")}); exactly one fixture may use match.type "default".`,
    );
  }
  if (defaults.length === 0) {
    throw new Error(
      `[mock-server] no fallback fixture found in ${dir}. Add one with { "match": { "type": "default" } }.`,
    );
  }

  return fixtures;
}
