// Runs ESLint into reports/frontend-ESLint_report.txt for local dev, so a
// single `npm run test:coverage` produces all four reports at once (mirrors
// the backend's pytest_sessionfinish hook for pylint).
//
// Skipped in CI: ci-frontend.yml's dedicated Lint step already produces this
// report and is the one that actually gates the build. This hook is
// advisory-only, so a local test run never fails because of an unrelated
// lint issue — same treatment pylint gets on the backend.
import { spawnSync } from "node:child_process";
import { mkdirSync } from "node:fs";

if (process.env.CI) {
  process.exit(0);
}

mkdirSync("reports", { recursive: true });

const result = spawnSync(
  "npx",
  ["eslint", ".", "-f", "stylish", "-o", "reports/frontend-ESLint_report.txt"],
  { stdio: "inherit", shell: true },
);

if (result.status !== 0) {
  console.warn(
    "[reports] ESLint reported issues — see reports/frontend-ESLint_report.txt",
  );
}
