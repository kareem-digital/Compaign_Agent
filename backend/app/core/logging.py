"""Logging: structured, correlated, and redacted.

Built on **structlog** driving stdlib `logging` handlers, rather than on either
alone. The reason is that this service logs from three kinds of caller and all
three must land in the same stream, redacted the same way:

  * our own code, via `logger.info("event", extra=kv(...))` - the house idiom;
  * new code that prefers native structlog binding, via `get_logger()`;
  * uvicorn, httpx and openai, which log through stdlib and know nothing about
    us.

`structlog.stdlib.ProcessorFormatter` is what unifies them: one processor chain
renders records from all three paths, so a credential in a uvicorn line is
scrubbed by the same code that scrubs one of ours.

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

**Scope: registry, validation, and failures. Nothing else.** Request timing,
node entry and exit, LLM calls and MCP calls are deliberately not logged - they
were removed rather than filtered, so there is no setting that brings them back.
Two consequences worth knowing before reading a log:

  * a quiet log means a working turn, not a missing one - a successful plan that
    hits a warm registry cache emits nothing at all;
  * no timing is recorded anywhere, so this stream cannot answer "why was that
    turn slow".

Level convention for what remains:

    DEBUG     full snapshot payloads (registry.sync.data)
    INFO      registry sync and validation outcomes
    WARNING   degraded but working - a source dropped, an item rejected
    ERROR     the turn failed, or reference data failed its integrity checks
    CRITICAL  wake someone: kill switch, tenant isolation breach

Usage:
    logger.info("registry.sync", extra=kv(version=3, markets=2, deals=41))

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
from typing import override

import structlog
from structlog.typing import EventDict

from app.core.context import current

# Anything that looks like a credential never reaches a log file.
#
# These are a backstop against accidental disclosure, not the primary control -
# the primary control is not putting secrets in log calls. Ordered cheapest
# first; every one runs against every rendered string.
_REDACTIONS = (
    (re.compile(r"sk-[A-Za-z0-9_\-]{8,}"), "sk-***REDACTED***"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+"), "Bearer ***REDACTED***"),
    (re.compile(r"(?i)(api[_-]?key\"?\s*[:=]\s*\"?)([A-Za-z0-9._\-]{8,})"), r"\1***REDACTED***"),
    # MCP auth token and OpenAI key as they appear in a settings dump or the
    # repr() of a config object. Both quote styles, because `repr()` produces
    # single quotes and JSON produces double.
    (
        re.compile(
            r"(?i)((?:mcp_auth_token|openai_api_key|password|secret)[\"']?\s*[:=]\s*[\"']?)"
            r"([^\s\"',}]{4,})"
        ),
        r"\1***REDACTED***",
    ),
)

# Field names whose *values* are secrets regardless of shape, scrubbed
# wholesale rather than pattern-matched. Catches `kv(headers={"Authorization":
# "..."})`, where the value may not look like a credential on its own.
_SECRET_FIELD_NAMES = frozenset(
    {
        "authorization",
        "api_key",
        "apikey",
        "openai_api_key",
        "mcp_auth_token",
        "token",
        "access_token",
        "password",
        "secret",
        "client_secret",
    }
)

# Keys the JSON payload owns. A kv() field of the same name would otherwise
# overwrite them - `kv(level=...)` silently relabelling an INFO line as DEBUG,
# for instance - so those get prefixed instead.
_RESERVED_PAYLOAD_KEYS = frozenset({"timestamp", "level", "logger", "event", "exception"})

# Identity fields, in the order they appear in a rendered line. Kept as a tuple
# because the JSON renderer emits them in this order and the over-budget path
# below keeps exactly these.
_IDENTITY_KEYS = (
    "timestamp",
    "level",
    "logger",
    "event",
    "request_id",
    "session_id",
    "advertiser_id",
)

# Rotation happens *before* a write, so one oversized record lands in a freshly
# rotated file and blows straight past the budget. At DEBUG we log whole MCP
# payloads, which against a real VOW server could be megabytes - so records are
# capped here rather than trusted to be small.
MAX_FIELD_CHARS = 2_000
MAX_LINE_BYTES = 32_000


def kv(**fields) -> dict:
    """Structured fields for one log call.

    Wraps the awkward `extra={"extra_fields": {...}}` shape:

        logger.info("stage.validation", extra=kv(market="US", blocking=0))

    Kept as-is through the structlog migration: it is the idiom every remaining
    call site uses, it reads well, and replacing it would gain nothing a
    processor cannot do.
    """
    return {"extra_fields": fields}


def get_logger(name: str | None = None):
    """A native structlog logger, for code that prefers `.bind()`.

    Interchangeable with `logging.getLogger` for our purposes - both render
    through the same processor chain and produce identical output.
    """
    return structlog.stdlib.get_logger(name)


def _redact(text: str) -> str:
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def _redact_value(value, key: str | None = None):
    """Scrub credentials and cap size anywhere inside a structured field.

    Recursive because DEBUG logs whole MCP and LLM payloads, and a credential
    nested three levels down is exactly the one that gets missed. The file is
    the copy that persists, so it must not be the unprotected one.

    Truncation is applied in the same pass: a value big enough to matter for
    the size budget is also too big to read.

    `key` lets a field be redacted by name as well as by shape - an opaque
    session token matches none of the patterns but is still a secret.
    """
    if key is not None and key.lower() in _SECRET_FIELD_NAMES and value is not None:
        return "***REDACTED***"
    if isinstance(value, str):
        clean = _redact(value)
        if len(clean) > MAX_FIELD_CHARS:
            return f"{clean[:MAX_FIELD_CHARS]}...[truncated {len(clean) - MAX_FIELD_CHARS} chars]"
        return clean
    if isinstance(value, dict):
        return {k: _redact_value(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_redact_value(v) for v in value]
    return value


# --- processors -------------------------------------------------------------
#
# Shared by both paths: native structlog calls and foreign stdlib records. They
# run in this order, and each assumes the previous one has run.


def _add_timestamp(_logger, _name, event_dict: EventDict) -> EventDict:
    event_dict["timestamp"] = datetime.now(UTC).isoformat()
    return event_dict


def _add_context(_logger, _name, event_dict: EventDict) -> EventDict:
    """Stamp correlation and span identifiers from the ambient context."""
    for key, value in current().items():
        event_dict.setdefault(key, value)
    return event_dict


def _merge_extra_fields(_logger, _name, event_dict: EventDict) -> EventDict:
    """Lift `kv()` fields off a stdlib record into the event dict.

    This is what keeps every existing `extra=kv(...)` call site working.
    Reserved names are prefixed rather than dropped, so a field is never
    silently lost and never silently overwrites the record's own identity.
    """
    record = event_dict.get("_record")
    fields = getattr(record, "extra_fields", None) if record is not None else None
    if not fields:
        return event_dict

    for key, value in fields.items():
        event_dict[f"field_{key}" if key in _RESERVED_PAYLOAD_KEYS else key] = value
    return event_dict


def _normalise_level(_logger, _name, event_dict: EventDict) -> EventDict:
    """Uppercase the level, matching what this service has always emitted.

    structlog's `add_log_level` writes the method name (`"info"`); the previous
    formatter wrote `record.levelname` (`"INFO"`). Downstream filters key on
    the latter.
    """
    level = event_dict.get("level")
    if isinstance(level, str):
        event_dict["level"] = level.upper()
    return event_dict


def _redact_all(_logger, _name, event_dict: EventDict) -> EventDict:
    """Redact and size-cap every value, including the event name itself."""
    for key in list(event_dict):
        if key.startswith("_"):
            continue
        if key == "event":
            event_dict[key] = _redact(str(event_dict[key]))
        elif key == "exception":
            event_dict[key] = _redact_value(event_dict[key])
        else:
            event_dict[key] = _redact_value(event_dict[key], key=key)
    return event_dict


# Annotated with structlog's own alias rather than left to inference: the local
# processors are written against plain `dict`, and an inferred heterogeneous
# tuple does not match the `Processor` signature structlog's own APIs ask for.
_SHARED_PROCESSORS: tuple[structlog.typing.Processor, ...] = (
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    _merge_extra_fields,
    _add_context,
    _add_timestamp,
    _normalise_level,
    structlog.processors.format_exc_info,
    _redact_all,
)


def _ordered_payload(event_dict: dict) -> dict:
    """Assemble the output dict: identity first, then fields, exception last."""
    payload: dict = {}
    for key in _IDENTITY_KEYS:
        value = event_dict.get(key)
        if value:
            payload[key] = value

    for key, value in event_dict.items():
        if key in _IDENTITY_KEYS or key == "exception" or key.startswith("_"):
            continue
        payload[key] = value

    if event_dict.get("exception"):
        payload["exception"] = event_dict["exception"]
    return payload


def _render_json(_logger, _name, event_dict: dict) -> str:
    """One JSON object per line. What the aggregator will eventually ingest."""
    payload = _ordered_payload(event_dict)

    line = json.dumps(payload, default=str)
    if len(line.encode("utf-8")) <= MAX_LINE_BYTES:
        return line

    # Still too big even after per-field capping - many fields rather than one
    # huge one. Keep the identity of the record and drop the payload, saying so,
    # rather than writing a line that breaks the size budget.
    kept = {key: payload[key] for key in _IDENTITY_KEYS if key in payload}
    kept["truncated"] = (
        f"dropped {len(payload) - len(kept)} field(s): record over {MAX_LINE_BYTES} bytes"
    )
    return json.dumps(kept, default=str)


def _render_text(_logger, _name, event_dict: dict) -> str:
    """Human-readable, with the session ID and structured fields kept inline."""
    payload = _ordered_payload(event_dict)

    stamp = datetime.now(UTC).strftime("%H:%M:%S")
    level = str(payload.pop("level", "INFO"))
    name = str(payload.pop("logger", ""))
    event = str(payload.pop("event", ""))
    payload.pop("timestamp", None)

    base = f"{stamp} {level:<7} {name:<28} {event}"

    session = payload.pop("session_id", None)
    if session:
        base = f"{base}  [{str(session)[:8]}]"

    exception = payload.pop("exception", None)

    # Span position is useful inline while reading a live console, but the raw
    # request/advertiser IDs are noise there - they are in the JSON file.
    payload.pop("request_id", None)
    payload.pop("advertiser_id", None)

    if payload:
        base = f"{base}  " + " ".join(f"{k}={v}" for k, v in payload.items())
    if exception:
        base = f"{base}\n{exception}"
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


def _formatter(renderer) -> structlog.stdlib.ProcessorFormatter:
    """A formatter that renders both structlog and foreign stdlib records.

    `foreign_pre_chain` is the part that matters: it runs the shared processors
    over records from uvicorn, httpx and every `logging.getLogger()` call in
    this codebase, so they arrive at the renderer in the same shape as a native
    structlog event.
    """
    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=list(_SHARED_PROCESSORS),
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
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
    structlog.configure(
        processors=[
            *_SHARED_PROCESSORS,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(_formatter(_render_json if console_format == "json" else _render_text))

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
        file_handler.setFormatter(_formatter(_render_json))
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

    # Transport chatter, none of it ours and none of it interesting unless the
    # transport itself is the suspect. `httpcore` is the loudest by a wide
    # margin - it logs every connection and frame at DEBUG. `uvicorn.access`
    # duplicates the request line without the correlation IDs, so it is pure
    # repetition. `uvicorn.error` keeps its level, which is what carries
    # startup and shutdown.
    #
    # `openai._base_client` is on this list too, and silencing it costs
    # something: it is the logger that emits "Retrying request to
    # /chat/completions in Ns" at INFO, which is how a 25-second turn gets
    # explained - a failed first attempt pays its full timeout before the retry
    # starts. But at DEBUG the same logger dumps request options and response
    # headers for every call, and that drowns the registry and validation lines
    # this stream exists for. Chasing latency rather than reading a turn? Drop it
    # back to INFO instead of WARNING.
    for noisy in ("httpx", "httpcore", "uvicorn.access", "openai._base_client"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if log_file:
        _warn_if_over_budget(path, total_max_bytes)
