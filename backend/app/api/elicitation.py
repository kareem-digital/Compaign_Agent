"""Server-owned state for interactive chat elicitations.

This is deliberately an API concern, not a graph concern.  The graph decides
which field is needed; this module issues opaque option IDs, validates a reply
against those IDs, and remembers the status that the browser must render.

The in-memory implementation is the local/M1 seam.  Its public interface is
small enough to move to Postgres alongside the durable checkpointer without
changing the chat route.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any
from uuid import uuid4


class ElicitationError(Exception):
    """A client-visible error whose shape is defined by the UI contract."""

    def __init__(self, status: int, code: str, detail: str, **extra: Any) -> None:
        super().__init__(detail)
        self.status = status
        self.body = {"detail": detail, "code": code, **extra}


@dataclass
class _Elicitation:
    scope: str
    id: str
    prompt: str
    field: str | None
    select: str
    allow_custom: bool
    options: list[dict[str, Any]]
    status: str = "pending"
    answer: dict[str, Any] | None = None

    def public(self) -> dict[str, Any]:
        """The browser never receives model-facing option values."""
        return {
            "type": "options",
            "id": self.id,
            "prompt": self.prompt,
            "select": self.select,
            "allow_custom": self.allow_custom,
            "custom_placeholder": None,
            "allow_skip": False,
            "allow_reopen": False,
            "status": self.status,
            "options": [
                {
                    "id": option["id"],
                    "label": option["label"],
                    "description": option.get("description"),
                    "badge": option.get("badge"),
                }
                for option in self.options
            ],
            "answer": deepcopy(self.answer),
        }


class InMemoryInteractiveTurnStore:
    """Bounded enough for local development; replace with a durable repository later."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._elicitations: dict[str, _Elicitation] = {}
        self._responses: dict[tuple[str, str], dict[str, Any]] = {}

    def replay(self, scope: str, client_message_id: str | None) -> dict[str, Any] | None:
        if not client_message_id:
            return None
        with self._lock:
            response = self._responses.get((scope, client_message_id))
            return deepcopy(response) if response else None

    def remember_response(self, scope: str, client_message_id: str | None, response: dict) -> None:
        if not client_message_id:
            return
        with self._lock:
            self._responses[(scope, client_message_id)] = deepcopy(response)

    def supersede_pending(self, scope: str) -> list[dict[str, Any]]:
        with self._lock:
            changed = []
            for record in self._elicitations.values():
                if record.scope == scope and record.status == "pending":
                    record.status = "superseded"
                    changed.append(record.public())
            return changed

    def issue(
        self,
        scope: str,
        *,
        prompt: str,
        field: str | None,
        select: str,
        allow_custom: bool,
        options: list[dict[str, Any]],
    ) -> dict[str, Any]:
        record = _Elicitation(
            scope=scope,
            id=f"elc_{uuid4()}",
            prompt=prompt,
            field=field,
            select=select,
            allow_custom=allow_custom,
            options=options,
        )
        with self._lock:
            self._elicitations[record.id] = record
        return record.public()

    def answer(
        self,
        scope: str,
        *,
        elicitation_id: str,
        selected_option_ids: list[str],
        custom_text: str | None,
    ) -> tuple[str, dict[str, Any]]:
        with self._lock:
            record = self._elicitations.get(elicitation_id)
            if record is None or record.scope != scope:
                raise ElicitationError(404, "elicitation_not_found", "No such elicitation for this session")
            if record.status != "pending":
                raise ElicitationError(
                    409,
                    "elicitation_not_pending",
                    f"Elicitation is already {record.status}",
                    elicitation=record.public(),
                )

            known = {option["id"]: option for option in record.options}
            unknown = [option_id for option_id in selected_option_ids if option_id not in known]
            if unknown:
                raise ElicitationError(
                    422,
                    "invalid_option_id",
                    "Unknown option id",
                    unknown_option_ids=unknown,
                )
            if record.select == "single" and len(selected_option_ids) > 1:
                raise ElicitationError(
                    422, "invalid_option_id", "This question takes a single choice"
                )

            custom = (custom_text or "").strip()
            if custom and not record.allow_custom:
                raise ElicitationError(
                    422, "custom_not_allowed", "Custom answers are not accepted here"
                )
            if not selected_option_ids and not custom:
                raise ElicitationError(422, "empty_answer", "Select an option or type an answer")

            values = [str(known[option_id]["value"]) for option_id in selected_option_ids]
            if custom:
                values.append(custom)
            record.status = "answered"
            record.answer = {
                "selected_option_ids": selected_option_ids,
                "custom_text": custom or None,
                "answered_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            }
            text = f"{record.field or record.prompt}: {', '.join(values)}"
            return text, record.public()


interactive_turn_store = InMemoryInteractiveTurnStore()
