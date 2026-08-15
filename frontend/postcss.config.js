import tailwindcss from "@tailwindcss/postcss";

/**
 * Flattens cascade layers out of the embedded widget's stylesheet, reordering
 * its contents so the flattened file resolves to the same winners the layered
 * one did.
 *
 * Why flatten at all: the host (Tailwind 3.4, `important: true`) ships entirely
 * unlayered CSS, and an unlayered normal declaration beats a layered one
 * regardless of specificity. While the widget was layered, the host's preflight
 * won every collision inside our own subtree — `*{border-width:0}` beat
 * `.border`, `button{background-color:transparent}` beat `.btn`.
 *
 * Why reordering is required: flattening throws away layer precedence, so
 * source order becomes the only tiebreaker — and daisyUI 5's emitted order is
 * the opposite of its layer precedence. It nests
 * `daisyui > daisyui.l1 > daisyui.l1.l2 > daisyui.l1.l2.l3`, puts base
 * components (`.btn`) in the *deepest* layer and their modifiers (`.btn-primary`,
 * `.btn-square`, `.btn-sm`) one level up, and relies on the rule that a layer's
 * own rules outrank its sub-layers'. In the file, though, the deep blocks are
 * emitted last. Unwrapping in place therefore let `.btn` overwrite every
 * `.btn-*` modifier that came before it: `--btn-fg` fell back to base-content,
 * so `.btn-primary` rendered dark text on the primary fill, and `.btn-sm` /
 * `.btn-square` lost their sizing and padding.
 *
 * So: bucket every top-level node by its layer path, sort the buckets by real
 * cascade precedence, then emit them unwrapped. Ordering rules implemented
 * below, lowest precedence first:
 *   - layers rank in declaration order (an `@layer a, b;` statement or, absent
 *     one, first appearance), recursively at each level;
 *   - a layer's own rules outrank anything in its sub-layers, so a path that is
 *     a prefix of another ranks *higher*;
 *   - unlayered content (path `[]`, a prefix of everything) ranks highest,
 *     which is what keeps Tailwind's utilities — imported without `layer()` —
 *     above daisyUI's components.
 * Ties keep source order, since `Array.prototype.sort` is stable.
 *
 * Scoped to `widget.css` on purpose: `src/index.css` owns its document, has no
 * competing stylesheet, and keeps Tailwind's normal layering.
 */
const flattenLayersForEmbed = {
  postcssPlugin: "vow-flatten-cascade-layers-embed",
  OnceExit(root, { result }) {
    const from = (result.opts.from ?? "").split("?")[0].replace(/\\/g, "/");
    if (!from.endsWith("/widget.css")) return;

    // Index of each layer among its siblings, filled in declaration order.
    const indices = new Map();
    const nextIndex = new Map();
    const rank = (path) =>
      path.map((_, depth) => {
        const key = path.slice(0, depth + 1).join(".");
        if (!indices.has(key)) {
          const parent = path.slice(0, depth).join(".");
          const next = nextIndex.get(parent) ?? 0;
          nextIndex.set(parent, next + 1);
          indices.set(key, next);
        }
        return indices.get(key);
      });

    const names = (params) =>
      params
        .split(",")
        .map((name) => name.trim())
        .filter(Boolean);

    const preamble = [];
    const chunks = [];

    const collect = (container, path) => {
      for (const node of [...(container.nodes ?? [])]) {
        if (node.type === "atrule" && node.name === "layer") {
          // `@layer a, b;` carries no block — it only declares order.
          if (!node.nodes) {
            for (const name of names(node.params)) rank([...path, ...name.split(".")]);
            node.remove();
            continue;
          }
          const nested = [...path, ...names(node.params)[0].split(".")];
          rank(nested);
          collect(node, nested);
          node.remove();
          continue;
        }
        node.remove();
        if (node.type === "atrule" && /^(charset|import)$/.test(node.name)) {
          preamble.push(node);
        } else {
          // A `@layer` nested inside `@media`/`@supports` is unwrapped in place;
          // Tailwind and daisyUI don't emit any, and the enclosing block already
          // fixes its own ordering.
          node.nodes?.length &&
            node.walkAtRules("layer", (inner) =>
              inner.nodes ? inner.replaceWith(inner.nodes) : inner.remove(),
            );
          chunks.push({ rank: rank(path), node });
        }
      }
    };
    collect(root, []);

    chunks.sort((a, b) => {
      const shared = Math.min(a.rank.length, b.rank.length);
      for (let i = 0; i < shared; i++) {
        if (a.rank[i] !== b.rank[i]) return a.rank[i] - b.rank[i];
      }
      return b.rank.length - a.rank.length;
    });

    root.append(preamble, ...chunks.map((chunk) => chunk.node));
  },
};

/**
 * Tailwind v4 ships its own vendor prefixing (Lightning CSS), so `autoprefixer`
 * is gone. Deliberately the PostCSS plugin rather than `@tailwindcss/vite`:
 * `src/widget/widget.css` is consumed as `?inline` (see `widget/federated.tsx`),
 * and the PostCSS path leaves that transform pipeline exactly as it was.
 */
export default {
  plugins: [tailwindcss(), flattenLayersForEmbed],
};
