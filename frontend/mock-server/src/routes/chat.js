import { Router } from "express";

import { handleTurn } from "../domain/turn.js";
import { publicView } from "../domain/elicitation.js";
import { elicitationStore } from "../state/elicitationStore.js";
import { idempotencyStore } from "../state/idempotencyStore.js";
import { sequenceStore } from "../state/sequenceStore.js";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export function createChatRouter(fixtures) {
  const router = Router();
  const stores = { elicitationStore, idempotencyStore, sequenceStore };

  // Thin on purpose: every decision lives in `domain/`, which imports nothing
  // outside node:* and is therefore testable in CI without installing express.
  router.post("/sessions/chat", async (req, res) => {
    const { status, payload, delayMs, log } = handleTurn({
      body: req.body,
      fixtures,
      stores,
    });

    if (delayMs) await sleep(delayMs);
    console.log(`[mock-server] ${status} ${log}`);

    return res.status(status).json(payload);
  });

  /**
   * Dev-only: closes a question behind the UI's back so the 409 path is
   * curl-able without opening a second tab. Never deployed anywhere.
   */
  router.post("/_dev/elicitations/:id/expire", (req, res) => {
    const row = elicitationStore.get(req.params.id);
    if (!row) return res.status(404).json({ detail: "No such elicitation" });

    row.status = "expired";
    console.log(`[mock-server] expired elicitation ${row.id}`);
    return res.json({ elicitation: publicView(row) });
  });

  /** Dev-only: lists the rows this process holds, so you can find an id to expire. */
  router.get("/_dev/elicitations", (req, res) => {
    const sessionId = req.query.session_id;
    const rows = sessionId
      ? elicitationStore.bySession(sessionId)
      : elicitationStore.all();
    return res.json({ elicitations: rows.map(publicView) });
  });

  return router;
}
