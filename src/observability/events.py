import structlog

_configured = False


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog to emit JSON lines to stdout. Idempotent — safe to
    call from app startup AND the run-thread entry point (whichever comes first
    wins; later calls are no-ops).

    Uses structlog-native processors: the stdlib add_logger_name processor
    crashes on PrintLogger (no ``.name``), so the logger name is bound in
    ``get_logger`` instead.
    """
    global _configured
    if _configured:
        return
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(__import__("logging"), log_level, 20)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )
    _configured = True


def get_logger(name: str = "agent") -> structlog.BoundLogger:
    return structlog.get_logger(name).bind(logger=name)
