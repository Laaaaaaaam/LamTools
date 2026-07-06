"""Request-scoped context variables for structured logging."""

from contextvars import ContextVar

session_id_var: ContextVar[str] = ContextVar("session_id", default="-")


class SessionFilter:
    """Inject session_id from ContextVar into every LogRecord."""

    def filter(self, record: dict) -> bool:
        record.session_id = session_id_var.get("-")
        return True