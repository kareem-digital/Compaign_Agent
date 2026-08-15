import { Router } from "express";

const body = (status) => ({
  status,
  service: "vow-agent-mock-server",
  environment: "development",
  version: "0.1.0",
});

/** Mirrors backend/app/api/health.py so probes and smoke scripts behave the same. */
export function createHealthRouter() {
  const router = Router();

  router.get("/health/live", (_req, res) => res.json(body("ok")));
  router.get("/health/ready", (_req, res) => res.json(body("ready")));

  return router;
}
