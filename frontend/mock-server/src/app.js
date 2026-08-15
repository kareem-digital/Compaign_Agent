import cors from "cors";
import express from "express";

import { createChatRouter } from "./routes/chat.js";
import { createHealthRouter } from "./routes/health.js";

const API_PREFIX = "/api/v1";

export function createApp(fixtures) {
  const app = express();

  // Wildcard CORS: this is a localhost-only dev tool, never deployed.
  app.use(cors());
  app.use(express.json());

  app.use(API_PREFIX, createHealthRouter());
  app.use(API_PREFIX, createChatRouter(fixtures));

  app.use((_req, res) => res.status(404).json({ detail: "Not Found" }));

  return app;
}
