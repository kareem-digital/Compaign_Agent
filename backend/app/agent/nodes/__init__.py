"""Planning nodes, one module each.

Four of the thirteen stages in the confirmed v5 flow - the costless planning
prefix - plus `ask_for_missing`, which every gate diverts to when a stage
cannot proceed. Nothing here mutates anything in VOW or commits spend; the
first node that can do either is `create_strategy`, after plan approval, which
is not built yet.

Nodes that reach VOW - directly or through the grounded registry - are factories
(`make_*`) taking the client they need, so a test passes a fake in one line.
`extract_fields` and `ask_for_missing` need neither and are plain functions.
"""

from app.agent.nodes.ask_for_missing import ask_for_missing
from app.agent.nodes.collect_targeting import make_collect_targeting
from app.agent.nodes.deliver_plan import deliver_plan
from app.agent.nodes.extract_fields import extract_fields
from app.agent.nodes.plan_ready import plan_ready
from app.agent.nodes.planner import evaluate_state_and_plan, planner_node
from app.agent.nodes.predict_reach import make_predict_reach
from app.agent.nodes.select_inventory import make_select_inventory
from app.agent.nodes.suggest_audiences import make_suggest_audiences
from app.agent.nodes.validate_basics import make_validate_basics

__all__ = [
    "ask_for_missing",
    "deliver_plan",
    "evaluate_state_and_plan",
    "extract_fields",
    "make_collect_targeting",
    "make_predict_reach",
    "make_select_inventory",
    "make_suggest_audiences",
    "make_validate_basics",
    "plan_ready",
    "planner_node",
]
