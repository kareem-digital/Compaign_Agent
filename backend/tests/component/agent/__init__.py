"""Component tests for app.agent — LangGraph node/service orchestration.

Relocated from tests/unit/agent (that folder now just points here — see
Calyxio_VOW_QA_Testing_Reporting_Strategy.pdf §1, which classifies
LangGraph nodes as "Service / Component", not "Unit"). Nothing lives here
yet: app/agent/graph.py only has the greet/echo stub nodes. Once real
planning nodes land (M1), their branching logic (slot-filling, tier
routing, budget-split math, forecast repair-loop) belongs here, with tool
calls and the LLM mocked.
"""
