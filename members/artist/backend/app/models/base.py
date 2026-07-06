import uuid
from datetime import datetime, timezone


def gen_uuid() -> str:
    return str(uuid.uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
