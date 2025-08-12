from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Mapping, Optional


class JsonFormatter(logging.Formatter):
    """A minimal JSON formatter for structured logs."""

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        # Propagate extra attributes (service, trace_id, bank_id, endpoint, etc.)
        for key in ("service", "trace_id", "bank_id", "endpoint"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, separators=(",", ":"))


def configure_logging(fmt: str | None = None, *, service_name: str | None = None) -> None:
    """Configure root logger with plain text or JSON output.

    Args:
        fmt: 'json' or 'text'. Defaults to LOG_FORMAT env or 'text'.
        service_name: optional service label to inject into every log line.
    """

    fmt = (fmt or os.getenv("LOG_FORMAT", "text")).lower()
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Clear default handlers (uvicorn/gunicorn install their own).
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
        )
    root.addHandler(handler)

    if service_name:
        # Preserve original getLogger so we don't recurse after monkey-patch
        # Store original getLogger only once to avoid chaining patches
        if not hasattr(logging, "_orig_get_logger"):
            logging._orig_get_logger = logging.getLogger  # type: ignore
        _orig_get_logger = logging._orig_get_logger  # type: ignore

        def _get_logger(name: Optional[str] = None) -> logging.LoggerAdapter:  # type: ignore
            base_logger = _orig_get_logger(name) if name else root
            return logging.LoggerAdapter(base_logger, extra={"service": service_name})

        logging.getLogger = _get_logger  # type: ignore
