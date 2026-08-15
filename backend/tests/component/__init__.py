"""Component (service) tests.

Per Calyxio_VOW_QA_Testing_Reporting_Strategy.pdf §1: "Service / Component —
Django services, LangGraph nodes — pytest + mocks." This repo is FastAPI,
not Django, so read that as: service-class and LangGraph-node tests, with
their *collaborators* mocked (other services, tool wrappers, the LLM) —
not the raw HTTP transport.

Distinction from tests/unit: unit mocks the transport-level boundary
(e.g. httpx.AsyncClient — see tests/unit/tools/test_tools.py) to test one
adapter class's own logic (retries, pagination, header construction).
Component tests mock the next level up — other services/tools/the LLM —
to test one service or graph node's own orchestration/branching logic.

Empty today: only the greet/echo stub nodes exist (app/agent/graph.py).
The strategy doc's named future services — BriefInterpreterService,
AudienceRetrievalService, ForecastService, AudienceRepairService,
PlanValidationService, ExecutablePlanService, MediaActivationService,
DeliveryStateService — don't exist in this codebase yet; add a test
module here per service as each lands, e.g.:
    component/agent/test_audience_repair.py
        Input: audience too narrow, forecast reach = 0
        Expect: repair triggered, constraints broadened (mandatory
        restrictions preserved), forecast retried, decision recorded.
"""
