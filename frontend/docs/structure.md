# Folder structure

Naming, layering and file-placement rules for `src/`. `CLAUDE.md`'s Architecture
section covers *why* the API layer is shaped the way it is; this file covers
where things go and what to call them.

## Naming

- **Components are PascalCase** (`MessageBubble.tsx`), **hooks and lib modules
  are kebab-case** (`use-chat.ts`, `create-agent-client.ts`).
- **Tests are colocated**, never in a separate mirror tree: `Foo.tsx` +
  `Foo.test.tsx` side by side. The only exception is `src/test/` (shared
  helpers for those colocated tests) and the root `tests/` tree (cross-cutting
  suites — e2e, integration — that don't belong to one source file); see
  `tests/README.md` for that split and why it exists.

## The barrel rule

`index.ts` is re-exports only, never logic. This isn't just style: `vite.config.ts`'s
`COVERAGE_EXCLUDE` blanket-excludes `src/**/index.ts` from coverage, on the
assumption a barrel has no behavior to cover. A barrel that grows real logic
silently drops out of the coverage gate instead of failing it.

## Where a new module belongs

Single-purpose logic that has (or will have) its own test file gets a folder
under `lib/` with the logic in a named file plus an `index.ts` barrel —
`lib/api/{http.ts,errors.ts,index.ts}` and `lib/config/{config.ts,index.ts}`
are the pattern. Importers use the folder path (`@/lib/config`); the alias
resolves to the barrel automatically, so a later split into more files never
touches a call site. A genuinely trivial one-off (no growth expected, no
sibling files) can stay a loose file at `lib/`'s root — but that's the
exception, not the default.

## `lib/agent` vs `lib/api`

Two folders that sound similar and aren't: `lib/api/` is the generic HTTP
primitive (any JSON endpoint, timeouts, abort, `ApiError`); `lib/agent/` is the
domain-specific consumer of it (`AgentClient` contract, the factory, the
`POST /sessions/chat` wire mapping). See `CLAUDE.md`'s "API layer" section for
the full pipeline and the rules that keep the two from blurring together.

## `src/test/` vs `tests/`

Don't put co-located unit-test helpers in root `tests/` — they belong in
`src/test/` because `tsconfig.app.json` only includes `src`. See
`tests/README.md` for the full rationale.
