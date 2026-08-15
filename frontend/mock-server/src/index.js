import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { createApp } from "./app.js";
import { loadFixtures } from "./fixtures/loader.js";

const here = dirname(fileURLToPath(import.meta.url));
const fixturesDir = join(here, "..", "fixtures", "chat");
const port = Number(process.env.PORT) || 4100;

const fixtures = loadFixtures(fixturesDir);

createApp(fixtures).listen(port, () => {
  console.log(`[mock-server] ${fixtures.length} fixtures loaded from fixtures/chat`);
  console.log(`[mock-server] listening on http://localhost:${port}/api/v1`);
});
