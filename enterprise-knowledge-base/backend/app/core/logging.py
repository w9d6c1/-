"""结构化日志配置 (structlog)"""

import logging
import structlog

from app.core.config import settings
from app.core.middleware import request_id_var, thread_id_var


def add_context(logger, method_name, event_dict):  # type: ignore[no-untyped-def]
    event_dict["request_id"] = request_id_var.get()
    event_dict["thread_id"] = thread_id_var.get()
    return event_dict


def setup_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_context,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
            if settings.debug
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


logger = structlog.get_logger()
