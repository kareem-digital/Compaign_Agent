// Copies Vitest's Cobertura coverage output into the shared reports/ folder
// under the frontend- naming convention. Vitest/Istanbul coverage reporters
// can't be individually renamed via config — the cobertura reporter always
// writes coverage/cobertura-coverage.xml — so this runs after every
// `vitest run --coverage` (see package.json's `posttest:coverage` hook) to
// bridge that gap. Runs in both local dev and CI; not CI-gated, since nothing
// else produces this file.
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { join } from "node:path";

const SRC = join("coverage", "cobertura-coverage.xml");
const DEST_DIR = "reports";
const DEST = join(DEST_DIR, "frontend-Vitest_coverage.xml");

if (!existsSync(SRC)) {
  console.warn(`[reports] ${SRC} not found — skipping coverage XML copy.`);
  process.exit(0);
}

mkdirSync(DEST_DIR, { recursive: true });
copyFileSync(SRC, DEST);
console.log(`[reports] Copied ${SRC} -> ${DEST}`);
