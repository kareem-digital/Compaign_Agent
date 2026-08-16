"""The JSON contract, redaction, and the size budget.

These assert the *shape on disk*, not that logging happened. A downstream
aggregator keys on these field names, so a rename is a breaking change and
should fail here rather than in a dashboard three weeks later.
"""

import json
import logging

import pytest

from app.core import logging as applog
from app.core.context import bind, clear


def render(_message="test.event", _level=logging.INFO, **fields):
    """Render one record through the real formatter and parse it back.

    Leading underscores so the parameter names cannot collide with a field name
    under test - `render(event=...)` has to mean the kv field, not the message.
    """
    logger = logging.getLogger("app.test")
    record = logger.makeRecord(
        "app.test", _level, __file__, 1, _message, (), None, extra=applog.kv(**fields)
    )
    formatter = applog._formatter(applog._render_json)
    return json.loads(formatter.format(record))


@pytest.fixture(autouse=True)
def _configured():
    applog.configure_logging(level="DEBUG", console_format="json")
    yield
    clear()


class TestJsonContract:
    def test_identity_fields_present_and_ordered(self):
        bind(request_id="req-1", session_id="sess-1", advertiser_id="adv-1")
        out = render()
        assert list(out)[:7] == [
            "timestamp",
            "level",
            "logger",
            "event",
            "request_id",
            "session_id",
            "advertiser_id",
        ]

    def test_level_is_uppercase(self):
        # structlog writes the method name lowercase; the service has always
        # emitted levelname, and filters key on it.
        assert render(_level=logging.WARNING)["level"] == "WARNING"

    def test_kv_fields_are_merged(self):
        out = render(tool="vow.list_deals", duration_ms=42)
        assert out["tool"] == "vow.list_deals"
        assert out["duration_ms"] == 42

    def test_reserved_keys_are_prefixed_not_dropped(self):
        # kv(level=...) must not relabel the record, and must not vanish.
        out = render(level="sneaky", event="sneaky")
        assert out["level"] == "INFO"
        assert out["event"] == "test.event"
        assert out["field_level"] == "sneaky"
        assert out["field_event"] == "sneaky"


class TestRedaction:
    def test_api_key_pattern_in_message(self):
        out = render("leaked sk-abcdefgh12345678 here")
        assert "sk-abcdefgh12345678" not in out["event"]
        assert "REDACTED" in out["event"]

    def test_bearer_token_in_field(self):
        out = render(header="Bearer abc.def.ghi")
        assert "abc.def.ghi" not in out["header"]

    def test_secret_field_name_redacts_opaque_value(self):
        # The value matches no pattern - only the field name marks it.
        out = render(authorization="opaque-session-value")
        assert out["authorization"] == "***REDACTED***"

    def test_nested_secret_is_reached(self):
        out = render(body={"headers": {"Authorization": "whatever"}, "ok": [1, 2]})
        assert out["body"]["headers"]["Authorization"] == "***REDACTED***"
        assert out["body"]["ok"] == [1, 2]

    def test_settings_style_assignment(self):
        out = render(config="mcp_auth_token='s3cr3t-value'")
        assert "s3cr3t-value" not in out["config"]


class TestSizeBudget:
    def test_long_field_is_truncated(self):
        out = render(body="x" * (applog.MAX_FIELD_CHARS + 500))
        assert "truncated" in out["body"]
        assert len(out["body"]) < applog.MAX_FIELD_CHARS + 100

    def test_oversized_record_collapses_to_identity(self):
        bind(request_id="req-1")
        # Many fields, each individually under the per-field cap.
        fields = {f"f{i}": "y" * 1_500 for i in range(60)}
        out = render(**fields)
        assert "truncated" in out
        assert out["request_id"] == "req-1"
        assert out["event"] == "test.event"
        assert len(json.dumps(out).encode()) <= applog.MAX_LINE_BYTES


class TestForeignRecords:
    def test_printf_style_still_renders(self):
        # Pre-existing call sites and uvicorn both use %-formatting.
        logger = logging.getLogger("app.test")
        record = logger.makeRecord(
            "app.test", logging.INFO, __file__, 1, "hello %s", ("world",), None
        )
        out = json.loads(applog._formatter(applog._render_json).format(record))
        assert out["event"] == "hello world"

    def test_exception_is_formatted_and_redacted(self):
        logger = logging.getLogger("app.test")
        try:
            raise ValueError("token sk-abcdefgh12345678")
        except ValueError:
            import sys

            record = logger.makeRecord(
                "app.test", logging.ERROR, __file__, 1, "boom", (), sys.exc_info()
            )
        out = json.loads(applog._formatter(applog._render_json).format(record))
        assert "Traceback" in out["exception"]
        assert "sk-abcdefgh12345678" not in out["exception"]


def test_configure_logging_is_idempotent():
    root = logging.getLogger()
    applog.configure_logging(level="INFO", console_format="json")
    first = len(root.handlers)
    applog.configure_logging(level="INFO", console_format="json")
    assert len(root.handlers) == first, "handlers stacked - reloader would duplicate every line"


class TestConsoleAndFile:
    def test_text_renderer_is_readable_and_redacted(self):
        bind(session_id="sess-abcdefgh-1234", request_id="req-1")
        logger = logging.getLogger("app.test")
        record = logger.makeRecord(
            "app.test",
            logging.INFO,
            __file__,
            1,
            "mcp.call",
            (),
            None,
            extra=applog.kv(tool="vow.list_deals", token="Bearer abc.def.ghi"),
        )
        line = applog._formatter(applog._render_text).format(record)

        assert "mcp.call" in line
        assert "[sess-abc" in line, "short session id kept inline for scanning"
        assert "tool=vow.list_deals" in line
        assert "abc.def.ghi" not in line
        assert "req-1" not in line, "raw request id is noise on a console; it is in the JSON file"

    def test_file_handler_rotates_on_bytes_not_characters(self, tmp_path):
        # A pound sign costs two bytes and one character. The stdlib handler
        # compares characters, so a file of multi-byte events overshoots.
        path = tmp_path / "test.log"
        handler = applog.BoundedRotatingFileHandler(path, maxBytes=200, backupCount=1)
        handler.setFormatter(applog._formatter(applog._render_json))

        logger = logging.getLogger("app.rotation")
        logger.handlers = [handler]
        logger.propagate = False
        for _ in range(10):
            logger.warning("event.with.£.signs", extra=applog.kv(note="£" * 20))
        handler.close()

        written = sorted(tmp_path.glob("test.log*"))
        assert len(written) > 1, "did not rotate"
        for f in written:
            # One record may exceed the cap (rotation happens before a write),
            # but the file must not run away.
            assert f.stat().st_size < 200 * 4

    def test_file_output_is_json_even_when_console_is_text(self, tmp_path):
        applog.configure_logging(
            level="INFO", console_format="text", log_file=str(tmp_path / "vow.log")
        )
        logging.getLogger("app.test").info("turn.end", extra=applog.kv(stage="delivered"))
        for handler in logging.getLogger().handlers:
            handler.flush()

        content = (tmp_path / "vow.log").read_text().strip().splitlines()
        assert content, "nothing written"
        parsed = json.loads(content[-1])
        assert parsed["event"] == "turn.end"
        assert parsed["stage"] == "delivered"
