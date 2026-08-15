function matches(match, message) {
  const type = match.type ?? "contains";
  const caseSensitive = match.caseSensitive === true;

  if (type === "regex") {
    return new RegExp(match.value, caseSensitive ? "" : "i").test(message);
  }

  const haystack = caseSensitive ? message : message.toLowerCase();
  const needle = caseSensitive ? match.value : match.value?.toLowerCase();

  return type === "exact" ? haystack.trim() === needle.trim() : haystack.includes(needle);
}

/**
 * First fixture whose match predicate holds, by descending priority then
 * filename. Falls back to the `default` fixture, which the loader guarantees
 * exists.
 */
export function matchFixture(message, fixtures) {
  const candidates = fixtures
    .filter((f) => f.match.type !== "default")
    .sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0) || a.file.localeCompare(b.file));

  return (
    candidates.find((f) => matches(f.match, message)) ??
    fixtures.find((f) => f.match.type === "default")
  );
}
