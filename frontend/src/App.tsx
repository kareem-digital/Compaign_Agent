import { VowAgentWidget } from "@/widget";

/**
 * Standalone shell. Page-level concerns (filling the viewport) live here so
 * the widget itself stays embeddable.
 */
export default function App() {
  return (
    <main className="flex min-h-0 flex-1 flex-col">
      <VowAgentWidget />
    </main>
  );
}
