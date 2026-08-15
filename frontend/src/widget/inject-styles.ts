const STYLE_ELEMENT_ID = "vow-agent-widget-styles";

/**
 * Adds the widget's compiled CSS to a document exactly once.
 *
 * A federated remote can't rely on the host to load its stylesheet: the MF
 * plugin leaves CSS assets off exposed modules unless `bundleAllCSS` is set,
 * and a host that mounts the widget lazily would otherwise render it unstyled.
 * The CSS arrives as a string (`widget.css?inline`) so there is no second
 * request to a URL that would have to be resolved against the remote's origin.
 *
 * Idempotent by element id, so several widget instances — or a remount after
 * HMR — share one `<style>` tag.
 *
 * @param doc Defaults to the ambient document; `null` (no DOM, e.g. an SSR
 *   pass on the host) makes this a no-op rather than a crash on import.
 */
export function injectWidgetStyles(
  css: string,
  doc: Document | null = globalThis.document ?? null,
): HTMLStyleElement | null {
  if (!doc || !css) return null;

  const existing = doc.getElementById(STYLE_ELEMENT_ID);
  if (existing) return existing as HTMLStyleElement;

  const style = doc.createElement("style");
  style.id = STYLE_ELEMENT_ID;
  style.textContent = css;
  // Prepended so the host's own stylesheets keep the last word on anything
  // that does collide, rather than the remote silently overriding them.
  //
  // This is load-bearing, not a nicety. The embed stylesheet is emitted with no
  // cascade layers (see `widget.css`), so it competes with the host purely on
  // specificity and source order — and it ships Tailwind v4 utilities whose
  // class names (`.flex`, `.p-2`, `.shadow-sm`) also match the host's own
  // elements, sometimes with different values across the two Tailwind majors.
  // Going first means the host's later, `important:true` rules keep winning on
  // its own markup. Switching this to `append` would let the remote restyle the
  // page around it.
  doc.head.prepend(style);
  return style;
}

export { STYLE_ELEMENT_ID };
