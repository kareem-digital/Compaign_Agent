import "@testing-library/jest-dom/vitest";

// jsdom implements neither of these, and both are used by the chat UI.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
