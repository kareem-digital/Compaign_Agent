"""Logging: structured, correlated, and redacted.

Two destinations, deliberately different:

  * **Console** - text by default, because you read it while you work.
  * **File** - always JSON, because a log aggregator will read it. Datadog is
    the plan; writing JSON now means switching to it is configuration rather
    than a rewrite.

Three things every record gets automatically:

  * **Correlation** - `request_id`, `session_id`, `advertiser_id` from
    `app.core.context`, so one conversation can be pulled out of the stream.
  * **Redaction** - API keys and bearer tokens are scrubbed from the rendered
    message as a backstop. One careless `logger.info(headers)` is all it takes.
  * **Structured fields** - via the `kv()` helper below.

Level convention for this service:

    DEBUG     full payloads: MCP bodies, LLM prompts, extracted values
    INFO      the narrative of a turn: stages entered, gates, calls, timings
    WARNING   degraded but working - a human should eventually look
    ERROR     the turn failed - a human must look
    CRITICAL  wake someone: kill switch, tenant isolation breach

If everything is INFO, nobody reads INFO. Keep the split honest.

Usage:
    logger.info("mcp.call", extra=kv(tool="vow.list_deals", duration_ms=42))

Message strings are dotted event names rather than sentences, so they group and
filter cleanly once this reaches an aggregator.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

# typing_extensions rather than typing: `override` is 3.12+ in the stdlib and
# CI runs 3.11. Already a dependency via app/agent/state.py.
from typing_extensions import override

from app.core.context import current

# Anything that looks like a credential never reaches a log file.
_REDACTIONS = (
    (re.compile(r"sk-[A-Za-z0-9_\-]{8,}"), "sk-***REDACTED***"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+"), "Bearer ***REDACTED***"),
    (re.compile(r"(?i)(api[_-]?key\"?\s*[:=]\s*\"?)([A-Za-z0-9._\-]{8,})"), r"\1***REDACTED***"),
)

# Keys the JSON payload owns. A kv() field of the same name would otherwise
# overwrite them - `kv(level=...)` silently relabelling an INFO line as DEBUG,
# for instance - so those get prefixed instead.
_RESERVED_PAYLOAD_KEYS = frozenset({"timestamp", "level", "logger", "event", "exception"})

# Rotation happens *before* a write, so one oversized record lands in a freshly
# rotated file and blows straight past the budget. At DEBUG we log whole MCP
# payloads, which against a real VOW server could be megabytes - so records are
# capped here rather than trusted to be small.
MAX_FIELD_CHARS = 2_000
MAX_LINE_BYTES = 32_000


def kv(**fields) -> dict:
    """Structured fields for one log call.

    Wraps the awkward `extra={"extra_fields": {...}}` shape:

        logger.info("turn.end", extra=kv(session="abc", duration_ms=91))
    """
    return {"extra_fields": fields}


def _redact(text: str) -> str:
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def _redact_value(value):
    """Scrub credentials and cap size anywhere inside a structured field.

    Recursive because DEBUG logs whole MCP and LLM payloads, and a credential
    nested three levels down is exactly the one that gets missed. The file is
    the copy that persists, so it must not be the unprotected one.

    Truncation is applied in the same pass: a value big enough to matter for
    the size budget is also too big to read.
    """
    if isinstance(value, str):
        clean = _redact(value)
        if len(clean) > MAX_FIELD_CHARS:
            return f"{clean[:MAX_FIELD_CHARS]}...[truncated {len(clean) - MAX_FIELD_CHARS} chars]"
        return clean
    if isinstance(value, dict):
        return {k: _redact_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_redact_value(v) for v in value]
    return value


class ContextFilter(logging.Filter):
    """Stamps the current correlation IDs onto every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in current().items():
            setattr(record, key, value)
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line. What the aggregator will eventually ingest."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": _redact(record.getMessage()),
        }

        for key in ("request_id", "session_id", "advertiser_id"):
            value = getattr(record, key, None)
            if value:
                payload[key] = value

        for key, value in getattr(record, "extra_fields", {}).items():
            if key in _RESERVED_PAYLOAD_KEYS:
                key = f"field_{key}"
            payload[key] = _redact_value(value)

        if record.exc_info:
            payload["exception"] = _redact_value(self.formatException(record.exc_info))

        line = json.dumps(payload, default=str)
        if len(line.encode("utf-8")) <= MAX_LINE_BYTES:
            return line

        # Still too big even after per-field capping - many fields rather than
        # one huge one. Keep the identity of the record and drop the payload,
        # saying so, rather than writing a line that breaks the size budget.
        kept = {
            key: payload[key]
            for key in (
                "timestamp",
                "level",
                "logger",
                "event",
                "request_id",
                "session_id",
                "advertiser_id",
            )
            if key in payload
        }
        kept["truncated"] = (
            f"dropped {len(payload) - len(kept)} field(s): record over {MAX_LINE_BYTES} bytes"
        )
        return json.dumps(kept, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable, with the session ID and structured fields kept inline."""

    def __init__(self):
        super().__init__("%(asctime)s %(levelname)-7s %(name)-28s %(message)s", "%H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        base = _redact(super().format(record))

        session = getattr(record, "session_id", None)
        if session:
            base = f"{base}  [{str(session)[:8]}]"

        fields = getattr(record, "extra_fields", {})
        if fields:
            rendered = " ".join(f"{k}={_redact_value(v)}" for k, v in fields.items())
            base = f"{base}  {rendered}"

        return base


class BoundedRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler that measures bytes and complains when it cannot rotate.

    Two fixes over the standard handler:

    **Bytes, not characters.** The stdlib compares `len(msg)` against a byte
    limit. A pound sign or an accented market name costs more bytes than
    characters, so the file quietly overshoots.

    **Rotation failures are visible.** On Windows a rename fails while another
    process holds the file - an editor with the log open, or a forgotten
    `Get-Content -Wait`. The stdlib swallows that and keeps appending, so the
    file grows past its limit with nothing to indicate why. We warn instead.

    On failure we keep writing rather than dropping records: an oversized file
    you have been warned about beats losing the log line that explains an
    outage. The warning prints once per failure run so it cannot be missed
    without being spam.
    """

    _rotation_failed = False

    # camelCase because these override stdlib `logging` methods, which predate
    # PEP 8. Renaming them to snake_case would stop them overriding anything -
    # the handler would silently revert to stock behaviour and the size budget
    # would stop being enforced. `@override` records the intent and satisfies
    # the pep8-naming rule.
    @override
    def shouldRollover(self, record: logging.LogRecord) -> bool:
        if self.stream is None:
            self.stream = self._open()
        if self.maxBytes <= 0:
            return False

        message = self.format(record) + "\n"
        self.stream.seek(0, 2)
        return self.stream.tell() + len(message.encode("utf-8")) >= self.maxBytes

    @override
    def doRollover(self) -> None:
        try:
            super().doRollover()
            self._rotation_failed = False
        except OSError as exc:
            if not self._rotation_failed:
                self._rotation_failed = True
                sys.stderr.write(
                    f"\n*** LOG ROTATION FAILED: {self.baseFilename}\n"
                    f"*** {exc}\n"
                    "*** The log file will keep growing past its size budget. "
                    "Close whatever holds it open (editor, Get-Content -Wait) "
                    "and restart the service.\n\n"
                )
                sys.stderr.flush()


def _warn_if_over_budget(path: Path, budget: int) -> None:
    """Report a log directory that is already too big at startup.

    This is what you would see the morning after an editor blocked rotation
    overnight - otherwise the breach is invisible until the disk fills.
    """
    total = sum(f.stat().st_size for f in path.parent.glob(f"{path.name}*") if f.is_file())
    if total > budget:
        logging.getLogger(__name__).warning(
            "logging.over_budget",
            extra=kv(total_bytes=total, budget_bytes=budget, path=str(path.parent)),
        )


def configure_logging(
    level: str = "INFO",
    console_format: str = "text",
    log_file: str | None = None,
    total_max_bytes: int = 10_000_000,
    backup_count: int = 4,
) -> None:
    """Set up console and (optionally) file logging.

    `total_max_bytes` is the budget for everything in the log directory - the
    active file plus every backup - not the size of one file. That is the
    number people actually care about, and quoting a per-file limit hides a
    footprint `backup_count + 1` times larger.

    Safe to call more than once - handlers are replaced, not stacked, so the
    dev server's reloader does not end up printing every line five times.
    """
    context_filter = ContextFilter()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(JsonFormatter() if console_format == "json" else TextFormatter())
    console.addFilter(context_filter)

    handlers: list[logging.Handler] = [console]

    if log_file:
        path = Path(log_file)
        if not path.is_absolute():
            # Relative to the backend package root, so the file lands in the
            # same place whether uvicorn was started from backend/ or above it.
            path = Path(__file__).resolve().parent.parent.parent / path
        path.parent.mkdir(parents=True, exist_ok=True)

        # Split the total budget across the active file and its backups, so the
        # configured number is what ends up on disk.
        per_file = max(1024, total_max_bytes // (backup_count + 1))

        file_handler = BoundedRotatingFileHandler(
            path, maxBytes=per_file, backupCount=backup_count, encoding="utf-8"
        )
        # Always JSON on disk: this is the file a tool will read, not a person.
        file_handler.setFormatter(JsonFormatter())
        file_handler.addFilter(context_filter)
        handlers.append(file_handler)

    root = logging.getLogger()
    root.handlers.clear()
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(level.upper())

    # uvicorn keeps its own handlers; clear them so its output goes through
    # ours and picks up correlation and redaction too.
    for noisy in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logging.getLogger(noisy).handlers.clear()
        logging.getLogger(noisy).propagate = True

    # httpx logs every outbound request at INFO, which duplicates our own
    # MCP and LLM call lines. Only interesting when debugging the transport.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    if log_file:
        logging.getLogger(__name__).info(
            "logging.configured",
            extra=kv(
                log_level=level.upper(),
                log_path=str(path),
                budget_mb=round(total_max_bytes / 1_000_000, 1),
                files=backup_count + 1,
                per_file_mb=round(per_file / 1_000_000, 2),
            ),
        )
        _warn_if_over_budget(path, total_max_bytes)
