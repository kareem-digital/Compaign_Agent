"""AI / LLM evaluation suite.

Per Calyxio_VOW_QA_Testing_Reporting_Strategy.pdf §1/§3/§12: tools are
DeepEval (primary — response quality, hallucination, RAG/retrieval
metrics), Promptfoo (prompt regression — a Node CLI, invoked from CI,
not a pytest dependency here), Ragas (RAG-specific metrics: Context
Precision/Recall, Faithfulness, Answer Relevance), and custom pytest
evaluators for project-specific checks. Probabilistic, scored against
fixed golden datasets and explicit thresholds — kept separate from
deterministic tests.

Covers, once real planning nodes replace the current greet/echo stub
in app/agent/graph.py: prompt regression, response quality (LLM-as-
judge + human-reviewed benchmarks), hallucination rate, RAG/retrieval,
prompt-injection/jailbreak resistance, safety/toxicity, bias/fairness,
consistency, context-window/memory, tool-calling correctness, and
stage-by-stage agent-workflow assertions.

Project-specific examples from the strategy doc to build against:
brief extraction ("GBP 20k ... Prime Video UK next month" -> correct
budget/market/inventory/dates), missing-information behaviour (agent
asks follow-up rather than inventing budget/market), grounding
(AUD999 rejected when only AUD001-3 are valid — target: 0 hallucinated
IDs), and strategy diversity (three generated options must differ in
substance, each with valid IDs and reasoning).

Deterministic guardrails around the same nodes (schema, allowed IDs,
tool calls, approval requirements) belong in tests/unit or
tests/component instead, not here — see the Human Evaluation section
(PDF §3) for the subjective-quality review process that complements,
but does not replace, this automated layer.
"""
