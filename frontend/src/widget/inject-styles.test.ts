import { afterEach, describe, expect, it } from "vitest";

import {
  injectWidgetStyles,
  STYLE_ELEMENT_ID,
} from "@/widget/inject-styles";

const styleTags = () =>
  document.head.querySelectorAll(`#${STYLE_ELEMENT_ID}`);

afterEach(() => {
  document.head.querySelectorAll(`#${STYLE_ELEMENT_ID}`).forEach((el) => {
    el.remove();
  });
});

describe("injectWidgetStyles", () => {
  it("adds the stylesheet to the document head", () => {
    injectWidgetStyles(".vow-agent-widget{color:red}");

    expect(styleTags()).toHaveLength(1);
    expect(styleTags()[0]).toHaveTextContent(".vow-agent-widget{color:red}");
  });

  it("injects once no matter how many widgets mount", () => {
    const first = injectWidgetStyles(".a{}");
    const second = injectWidgetStyles(".b{}");

    expect(styleTags()).toHaveLength(1);
    // The first tag wins — re-injecting must not restyle a mounted widget.
    expect(second).toBe(first);
    expect(styleTags()[0]).toHaveTextContent(".a{}");
  });

  it("goes first in head so the host's stylesheets still take precedence", () => {
    const hostStyle = document.createElement("style");
    document.head.append(hostStyle);

    injectWidgetStyles(".a{}");

    expect(document.head.firstElementChild?.id).toBe(STYLE_ELEMENT_ID);
    hostStyle.remove();
  });

  it("no-ops without a document, so an SSR host can import the module", () => {
    expect(injectWidgetStyles(".a{}", null)).toBeNull();
    expect(styleTags()).toHaveLength(0);
  });
});
