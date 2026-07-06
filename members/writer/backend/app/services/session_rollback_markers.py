from __future__ import annotations

from typing import Any


ROLLBACK_METADATA_KEY = "rollback"
ROLLED_BACK_STATUS = "rolled_back"


def is_rolled_back_metadata(metadata: Any) -> bool:
    if not isinstance(metadata, dict):
        return False
    marker = metadata.get(ROLLBACK_METADATA_KEY)
    return isinstance(marker, dict) and marker.get("status") == ROLLED_BACK_STATUS


def with_rolled_back_metadata(metadata: Any, marker: dict[str, Any]) -> dict[str, Any]:
    result = dict(metadata or {}) if isinstance(metadata, dict) else {}
    result[ROLLBACK_METADATA_KEY] = {"status": ROLLED_BACK_STATUS, **marker}
    return result
