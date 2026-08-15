# Architecture

`CLAUDE.md` covers the API layer that already exists. This file covers **styling tokens**, **i18n** and
**responsive readiness**, where the target is partly aspirational — apply these rules to new code rather than
inferring them from existing code. **Precedence:** `CLAUDE.md` > `docs/architecture.md` > `docs/ui.md`; known
conflicts are flagged in place, so do not resolve a new one silently. Rules are binding now; work-lists are
existing violations — fix when touching that file, don't sweep the repo unasked.

---

## 1. Styling: one declared place per design value

Every colour, font, radius, size and duration is declared once as a named token, so changing all button
backgrounds is a one-line edit — never a search-and-replace.

1. **No `style={{}}` in JSX.** Currently zero occurrences; keep it that way. Sole exception: a value *measured
   from layout at runtime* (`ChatInput.tsx` setting `textarea.style.height` from `scrollHeight`). Its cap is
   still a token.
2. **No design values in class names** — `text-[0.9375rem]`, `max-w-[85ch]`, `bg-[#5b21b6]`, `h-[180px]` are
   banned. Arbitrary *variants* (`[&>svg]:size-4`) are fine.
3. **Three token files.** Put a token in the highest applicable layer. Only `themes.css` exists; create the
   others when first needed, wired per rule 5.

   | File | Holds | Per theme? |
   |---|---|---|
   | `src/styles/themes.css` | semantic colours, radii — `@plugin "daisyui/theme"` for `light`/`dark` | yes |
   | `src/styles/tokens.css` | theme-invariant brand scale — fonts, type steps, measures, z-index, motion, container sizes — via `@theme` | no |
   | `src/styles/components.css` | shared multi-property recipes, when a repeated *structure* needs one home | no |

4. **Escalation ladder for "change X everywhere"** — cheapest rung wins, and never skip down to copying a class
   string into N components. (a) A **semantic colour token** in `themes.css`: components use daisyUI semantic
   classes (`btn-primary`, `bg-base-100`), so editing `--color-primary` restyles every primary button in both
   themes, standalone and embedded, at runtime — this covers most cases. (b) A **brand token** in `tokens.css`
   for non-colour values. (c) A **shared recipe** in `components.css`, only when the change is structural
   (padding *and* shadow *and* border) and cannot be a token.
5. **A new stylesheet must be imported by *both* entry points** — `src/index.css` and `src/widget/widget.css`
   must never diverge on tokens. In `widget.css` it goes **before** `@import "tailwindcss/utilities.css"`; the
   ordering comments there and the flattening argument in `postcss.config.js` are load-bearing. Read both first.
6. **No `@layer` in anything the embed build consumes** — see the cascade-layer section of `CLAUDE.md`; the
   widget ships unlayered on purpose. The flattening in `postcss.config.js` *reorders* by cascade precedence
   before unwrapping, because daisyUI 5 emits its blocks in the opposite order to their layer precedence.
   A hand-written `@layer` would be silently re-sorted by that pass; author unlayered CSS instead.
7. **daisyUI internals are not a token API.** Style through semantic tokens and documented classes; its
   component-level properties move across majors.
8. **Anything that preflight puts on `html`/`body` must be restated on `.vow-agent-widget`.** The embed build
   compiles preflight out, so inheritable properties — `font-size`, `line-height`, `font-family`, `color` — come
   from the *host's* `body` unless our root sets them. Use relative units (`1rem`, not `16px`) so a host that
   scales the root for accessibility still scales the widget.

**Decision: CSS custom properties, not `variables.scss`.** Same goal — one declared home per value — but strictly
more capable here. **SCSS variables are compile-time**, so `data-theme="dark"` and the widget's `theme` prop could
not work; light/dark would need two stylesheets. **A host cannot override them**: the widget is injected as
compiled CSS (`widget/inject-styles.ts`), and a host can retheme custom properties but not values already inlined
by Sass. **The token layer already exists** — Tailwind v4 `@theme` and daisyUI 5 `@plugin "daisyui/theme"` *are*
the declaration mechanism and generate the utilities, so a parallel SCSS scale is a second source of truth. And
**it costs a `sass` dependency**, against the lean-dependency constraint that exists because Module Federation
shares what we ship. If SCSS is later mandated for host-repo parity, the only safe shape is SCSS *authoring* that
emits custom properties — never `$color-primary: #5b21b6` used directly in a rule.

**Work-list.** `ChatInput.tsx` has two disagreeing caps for one behaviour — `MAX_ROWS_HEIGHT_PX = 180` and
`max-h-44` (176px), where CSS wins; collapse to one token. `ChatInput.tsx:82` and `MessageBubble.tsx:25` duplicate
`sm:text-[0.9375rem]` (should be one message-body type token); the same line's `max-w-[85ch]` is a reading measure.
Long repeated class strings in `WelcomeScreen.tsx` and `ChatInput.tsx` are rung-3 candidates once a second call
site appears.

---

## 2. Internationalisation

Only `en` ships and no i18n layer exists yet. Build the below when the first string moves; conform now to **no
user-facing string hard-coded in `.tsx`**.

- **Content lives in `src/locales/en/*.json`** — `common`, `chat`, `layout`, `errors`, namespaced to match
  `src/components/`, re-exported by `index.ts`. Dotted keys: `chat.input.placeholder`. `en` is source of truth
  *and* fallback; a key missing from `en` must fail a test, not render blank.
- **Access via `const { t } = useTranslation()`**, with `t(key, vars?) => string` and `{{name}}` interpolation.
  `TranslationKey` is derived from the `en` bundle by a recursive key-path type, so a typo is a compile error —
  the main reason to own this layer.
- **Values are plain text.** No HTML in a translation string; that reintroduces the `dangerouslySetInnerHTML`
  risk `CLAUDE.md` bans. Compose rich text from multiple keys.
- **Locale is injected, never build-time** — same reason as `apiBaseUrl`/`theme`, since one bundle serves many
  hosts. Add `locale?: string` to `VowAgentWidgetProps` and mount `I18nProvider` beside `AgentClientProvider`.
  Resolution: prop → host `<html lang>` → `navigator.language` → `en`. Unknown values fall back, never throw.
- **Never translate** `data-testid`, logs, `X-Request-ID`, or wire values (`role`, `stage`, `session_id`) —
  protocol, not copy.
- **Agent replies pass through as-is** (the backend owns their language). Errors differ: never render a raw
  backend `detail` as our own copy — map `ApiError` to a key in `errors.json`, showing raw detail only under
  `import.meta.env.DEV`.
- **Use logical utilities** in new markup — `ps-*`/`pe-*`, `ms-*`/`me-*`, `text-start`/`text-end`, not
  `pl-*`/`text-left`. Free now, expensive to retrofit.
- **Tests** mount the provider in `src/test/render.tsx` and assert on resolved English, **not on keys** — a key
  assertion passes when the key is missing. Add one test that every non-`en` bundle matches `en`'s key set.

**Decisions.** *In-house provider, not `react-i18next`*: today's need is keyed lookup with interpolation, and the
library is a dependency MF must share — shape the API like i18next's so adopting it later is a provider swap, not
a call-site sweep. Revisit for plural categories beyond one/other, gender/ordinal selection, or translator
tooling. *Static registry while there is one locale*: `MESSAGES: Record<Locale, Messages>`, no async machinery;
locale #2 means lazy loaders plus a provider fallback state, confined to one file — which is the point.

**Formatting.** `formatTime` in `lib/utils.ts` passes `[]` for locale, i.e. *browser* locale, which will diverge
from the injected app locale — it must take the active locale. **Known conflict with `docs/ui.md`:** the mandated
`do MMM yyyy` is English-ordinal specific and can't be reused for another locale, and `date-fns` needs its
`locale` option set too. When a second locale lands the format string becomes a per-locale bundle entry; until
then `do MMM yyyy` stands.

**Work-list.** Hard-coded copy to move: `WelcomeScreen.tsx` (`SUGGESTED_PROMPTS`, `h1`, description);
`ChatInput.tsx` (`sr-only` label, placeholder, `aria-label`, both keyboard hints, counter);
`MessageBubble.tsx` (`"You"`/`"VOW Agent"`); `config.ts` `appTagline` → `layout.json` (`appName` is brand
identity, stays); `ChatContainer.tsx` renders `error` verbatim — route it through the `errors.json` mapping.

---

## 3. Responsive: not supported, but architected for

**Declared support: desktop only**; small viewports are not QA'd. The goal is that enabling support later means
adding rules and testing them, never restructuring.

**The key decision: container queries, not viewport media queries.** A host may mount the widget in a 400px side
panel inside a 2560px browser, so **viewport width is the wrong signal** — `sm:` asks about the window, not the
box we were given, and a narrow panel on a wide monitor gets the wide layout and breaks.

1. **Use container-query variants** (`@sm:`, `@md:`), not viewport ones. Tailwind v4 ships these natively.
2. **The widget root establishes a *named* container** — `@container/vow-agent` on `.vow-agent-widget`, queried as
   `@sm/vow-agent:`. Unnamed resolves to the nearest ancestor container, which in a host page could be the host's.
3. **Breakpoints come from `--container-*` tokens** in `tokens.css`. **Caveat:** in Tailwind v4 that scale also
   backs `max-w-*`, so add named steps rather than mutating stock ones.
4. **Never `100vh`** — meaningless in an embedded subtree. Extend the existing `flex` + `min-h-0` chain (why
   `body`/`#root` are flex columns) instead of measuring the window.
5. **No JS for layout** (`innerWidth`, `matchMedia`, UA sniffing, `react-responsive`) and **one component per
   surface** — no `MobileChatInput`, no mobile route, no device-conditional trees.
6. **Controls size from a token with a ≥44px hit area**, even desktop-only; retrofitting hit targets across every
   control is the expensive part.
7. **Overflow belongs to the scroll container**, never the page, so an embedded widget never scrolls its host —
   `ChatContainer` already owns the single scroll region. **Author mobile-first**: unprefixed = narrow case.

**Ready to adopt when** breakpoints live in one file, every responsive rule is container-relative, spacing uses
logical properties, no fixed px width sits outside `tokens.css`, every control's size traces to a token, and
there is one component tree.

**Work-list.** Viewport `sm:` usages to migrate: `ChatContainer.tsx:26`, `ChatInput.tsx:82,107,110`,
`MessageBubble.tsx:25`, `WelcomeScreen.tsx:23,32,34`, `Header.tsx:27,35`. `ChatInput.tsx:107-110` is the sharpest —
`hidden sm:inline` / `sm:hidden` swaps the keyboard hint on *window* width, so an embedded narrow panel on a
desktop shows the long hint it has no room for. Logical-property fixes: `text-left`, `justify-start`
(`WelcomeScreen.tsx`), `ml-2` (`MessageBubble.tsx`).

---

## Review checklist

- [ ] no `style={{}}`, no design value inside `[...]`; every colour/size/duration is a token in the highest layer
- [ ] a new stylesheet is imported by **both** entry points, correctly ordered, with no `@layer` in the embed path
- [ ] no user-facing string literal in `.tsx`
- [ ] responsive rules container-relative, breakpoints tokenised, spacing logical
- [ ] daisyUI components (`docs/ui.md`), dates via `date-fns`; typecheck, lint and tests pass
