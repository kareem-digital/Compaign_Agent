import { createReadStream, existsSync, statSync } from "node:fs";
import { join, normalize, sep } from "node:path";
import { fileURLToPath, URL } from "node:url";

import { federation } from "@module-federation/vite";
import react from "@vitejs/plugin-react";
// Not re-exported by vitest/config.
import { loadEnv } from "vite";
// From vitest/config so the `test` block below is typed.
import {
  coverageConfigDefaults,
  defineConfig,
  type Plugin,
} from "vitest/config";

// Shared by the app build and the Vitest run so imports resolve identically
// in both. Kept manual rather than pulling in vite-tsconfig-paths.
const alias = {
  "@": fileURLToPath(new URL("./src", import.meta.url)),
};

/**
 * `--mode remote` builds/serves this app as a Module Federation remote instead
 * of a standalone SPA. Same source, same components; what changes is the entry
 * (`src/widget/federated.tsx` rather than `index.html`), the CSS (embed-safe —
 * see `docs/architecture.md`'s styling section and `postcss.config.js`), and
 * the port, so the remote dev server can run alongside a host that also wants
 * :3000.
 */
const REMOTE_PORT = 3001; // Todo: for dev purpose only. will changes later once prod deployment is finalized

/** Host-side counterpart: `remotes: { vow_agent: … }`. Renaming breaks hosts. */
const REMOTE_NAME = "vow_agent";

/**
 * Both builds are served from one origin under separate context paths, and the
 * output directories mirror those paths exactly (`dist/agent`, `dist/mfe`) so
 * `nginx.conf` needs a `root` and nothing else — no `alias` rewriting.
 *
 *   /agent/              standalone SPA
 *   /mfe/remoteEntry.js  federation entry, the URL hosts pin
 */
const STANDALONE_BASE = "/agent/";
const REMOTE_BASE = "/mfe/";
const DEV_PORT = 3000; // Todo: for dev purpose only. will changes later once prod deployment is finalized

const REMOTE_OUT_DIR = "dist/mfe";

/**
 * Files with no behaviour a test could assert: entry points, barrels, type-only
 * modules and the test helpers themselves. Excluded rather than left sitting at
 * 0%, so the thresholds below measure code that tests can actually reach.
 */
const COVERAGE_EXCLUDE = [
  "src/main.tsx", // ReactDOM bootstrap; needs a real index.html to mean anything
  "src/App.tsx", // three lines of layout around <VowAgentWidget />
  "src/setupTests.ts",
  "src/test/**", // shared render helper and fixture factories
  "src/**/index.ts", // barrels — re-exports only, no logic
  "src/types/**", // type-only
  "src/lib/agent/types.ts", // the AgentClient contract, type-only
  "src/lib/agent/wire.ts", // wire shapes, type-only
  // Module Federation entry: side-effectful by design, and it imports
  // `./widget.css?inline`, which `css: false` leaves unresolved under Vitest.
  // Both of its moving parts are covered directly instead — see
  // `inject-styles.test.ts` and `VowAgentWidget.test.tsx`.
  "src/widget/federated.tsx",
];

const MIME: Record<string, string> = {
  ".js": "application/javascript",
  ".mjs": "application/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".woff2": "font/woff2",
  ".woff": "font/woff",
  ".svg": "image/svg+xml",
  ".map": "application/json",
};

/**
 * Serves the built remote (`dist/mfe`) at `/mfe/` from the standalone dev
 * server, so one process covers both context paths on one origin.
 *
 * This is deliberately static rather than a proxy to a second dev server. Two
 * dev servers would be needed to give the remote HMR — the embed build flips
 * Tailwind's preflight and daisyUI's base layer through a *process-global*
 * env var (see `VOW_AGENT_EMBED` below), so one process cannot compile both
 * variants. Static serving avoids that entirely and matches what nginx does in
 * production, which is the behaviour worth reproducing in dev.
 *
 * The trade: `/mfe/` reflects the last `npm run build:remote`, not live source.
 * Run `npm run dev:remote` on its own port when actively iterating on the
 * widget *as a remote*.
 */
function serveBuiltRemote(): Plugin {
  const root = fileURLToPath(new URL(`./${REMOTE_OUT_DIR}`, import.meta.url));

  return {
    name: "vow-agent-serve-built-remote",
    apply: "serve",
    configureServer(server) {
      // No `next`: every path below terminates the response. Falling through
      // is exactly the failure this middleware exists to prevent.
      server.middlewares.use(REMOTE_BASE, (req, res) => {
        // Strip the query string; `?inline` and friends never reach disk.
        const rel = decodeURIComponent((req.url ?? "/").split("?")[0]);

        // Contain the path: a resolved target outside `root` is traversal.
        const target = normalize(join(root, rel));
        if (target !== root && !target.startsWith(root + sep)) {
          res.statusCode = 403;
          return res.end("Forbidden");
        }

        if (!existsSync(target) || !statSync(target).isFile()) {
          if (!existsSync(root)) {
            res.statusCode = 503;
            res.setHeader("Content-Type", "text/plain");
            return res.end(
              `The remote is not built. Run \`npm run build:remote\` to populate ${REMOTE_OUT_DIR}.\n`,
            );
          }
          // 404 rather than next(): falling through would let the SPA's
          // index.html answer a .js request, which surfaces as the classic
          // "Unexpected token '<'" instead of a missing-chunk error.
          res.statusCode = 404;
          return res.end("Not found");
        }

        const ext = target.slice(target.lastIndexOf("."));
        res.setHeader("Content-Type", MIME[ext] ?? "application/octet-stream");
        // Mirrors nginx: hosts on another dev origin fetch these directly.
        res.setHeader("Access-Control-Allow-Origin", "*");
        // Never cache in dev — a rebuilt remote must be picked up on reload.
        res.setHeader("Cache-Control", "no-store");
        createReadStream(target).pipe(res);
      });
    },
  };
}

export default defineConfig(({ command, mode }) => {
  const isRemote = mode === "remote";
  const isServe = command === "serve";

  // Same-origin in the browser, forwarded server-to-server here — sidesteps
  // the backend's CORS allowlist (../backend/app/config.py) for local dev.
  const env = loadEnv(mode, process.cwd(), "");
  const proxy = {
    "/api": {
      target: env.VITE_API_PROXY_TARGET || "http://localhost:8000",
      changeOrigin: true,
    },
  };

  // Tailwind's config is loaded by PostCSS later in this same process, and it
  // has no other way to know which build it is compiling for.
  if (isRemote) {
    process.env.VOW_AGENT_EMBED = "true";
  }

  return {
    // Relative base makes every chunk and font URL resolve against the module's
    // own location (`import.meta.url`), so the remote works from whatever
    // origin or path it happens to be deployed to — the host's origin is not
    // knowable at build time. That is what lets the same remote bundle sit at
    // `/mfe/` with no rebuild.
    //
    // Dev is the exception: a dev server has no module-relative notion for its
    // own entry, so it serves under the literal prefix instead. That keeps the
    // remote at `/mfe/remoteEntry.js` on every surface — the standalone dev
    // server, the dedicated remote dev server, and nginx.
    base: isRemote ? (isServe ? REMOTE_BASE : "./") : STANDALONE_BASE,
    plugins: [
      react(),
      ...(isRemote
        ? [
            federation({
              name: REMOTE_NAME,
              filename: "remoteEntry.js",
              exposes: {
                "./VowAgentWidget": "./src/widget/federated.tsx",
              },
              // Singletons, because two React copies on one page break hooks.
              // The host pins the same versions (React 18.2).
              shared: {
                react: { singleton: true, requiredVersion: "^18.2.0" },
                "react-dom": { singleton: true, requiredVersion: "^18.2.0" },
              },
              // Types are hand-written on the host side (one small module
              // declaration) rather than fetched over the network at build time.
              dts: false,
            }),
          ]
        : // Standalone dev serves the built remote at /mfe/ so a single
          // process covers both context paths on one origin.
          [serveBuiltRemote()]),
    ],
    resolve: { alias },
    server: isRemote
      ? {
          port: REMOTE_PORT,
          strictPort: true,
          // A host on another origin has to be allowed to fetch remoteEntry.js,
          // and dev asset URLs have to be absolute for the same reason.
          cors: true,
          origin: `http://localhost:${REMOTE_PORT}`,
          proxy,
        }
      : {
          port: DEV_PORT,
          // A host app on its own dev port fetches the remote from this origin.
          cors: true,
          proxy,
        },
    preview: isRemote
      ? { port: REMOTE_PORT, strictPort: true, cors: true }
      : undefined,
    build: isRemote
      ? {
          outDir: "dist/mfe",
          // The federation runtime uses top-level await.
          target: "chrome89",
          rollupOptions: {
            // No index.html: this build output is a library for hosts, and the
            // standalone page it would emit here has the embed-safe CSS, which
            // is wrong for a page that owns the document.
            input: { "vow-agent-widget": "./src/widget/federated.tsx" },
          },
        }
      : // Siblings under one `dist/`, so the deployable tree is a single
        // directory whose layout already matches the served URLs. Vite empties
        // only its own outDir, so neither build clobbers the other.
        { outDir: "dist/agent" },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/setupTests.ts"],
      css: false,
      // Test-result reporters (distinct from the coverage reporters below).
      // `junit`/`html` are Vitest built-ins; `html` requires @vitest/ui.
      reporters: ["default", "junit", "html"],
      outputFile: {
        junit: "./reports/frontend-Vitest_report.xml",
        html: "./reports/frontend-Vitest_report.html",
      },
      coverage: {
        provider: "v8",
        // `cobertura` adds Cobertura-format XML coverage (matches backend's
        // coverage XML). Istanbul reporters can't be individually renamed —
        // it lands as coverage/cobertura-coverage.xml and gets copied to
        // reports/frontend-Vitest_coverage.xml by scripts/copy-coverage-report.mjs
        // (wired into the `posttest:coverage` npm hook).
        reporter: ["text", "html", "lcovonly", "json-summary", "cobertura"],
        reportsDirectory: "./coverage",
        include: ["src/**/*.{ts,tsx}"],
        exclude: [...coverageConfigDefaults.exclude, ...COVERAGE_EXCLUDE],
        all: true,
        reportOnFailure: true,
        thresholds: {
          lines: 80,
          statements: 80,
          functions: 80,
          branches: 80,
        },
      },
    },
  };
});
