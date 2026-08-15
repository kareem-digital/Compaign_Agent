/**
 * Module Federation entry — the module a host loads as
 * `vow_agent/VowAgentWidget`.
 *
 * It exists so the exposed surface can carry the one thing the standalone app
 * gets from `index.html` and a host cannot give us: the widget's stylesheet.
 * `App.tsx` deliberately does not go through here.
 *
 * A default export is part of the contract — it is what lets a host write
 * `lazy(() => import("vow_agent/VowAgentWidget"))` with no adapter module.
 */
import widgetStyles from "./widget.css?inline";
import { injectWidgetStyles } from "./inject-styles";
import { VowAgentWidget } from "./VowAgentWidget";

injectWidgetStyles(widgetStyles);

export { VowAgentWidget };
export type { VowAgentWidgetProps } from "./VowAgentWidget";
export default VowAgentWidget;
