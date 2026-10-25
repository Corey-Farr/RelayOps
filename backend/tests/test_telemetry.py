import json
import logging
import sys

from relayops.observability.telemetry import JSONFormatter


def test_exception_logging_keeps_diagnostics_without_exception_secrets():
    try:
        raise ValueError("password=private-value payload=private-payload")
    except ValueError:
        record = logging.LogRecord(
            "worker", logging.ERROR, __file__, 10, "Dispatch failed", (), sys.exc_info()
        )
    rendered = JSONFormatter().format(record)
    value = json.loads(rendered)
    assert value["exception_type"] == "ValueError" and value["timestamp"]
    assert (
        value["stack"][-1]["function"] == "test_exception_logging_keeps_diagnostics_without_exception_secrets"
    )
    assert "private-value" not in rendered and "private-payload" not in rendered
