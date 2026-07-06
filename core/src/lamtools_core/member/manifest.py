"""Member manifest — describes a single member of the LamTools Core."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class MemberManifest:
    """Describes a single member in the Core system.

    Attributes:
        id: Unique identifier for the member.
        name: Human-readable name.
        version: Semantic version string.
        display_name: Optional display name; defaults to ``name`` if empty.
        capabilities: List of capability descriptors.
        default_routes: Mapping of route prefix to description.
        config: Member-specific configuration.
        hooks: Startup/shutdown lifecycle hooks.
    """

    id: str
    name: str
    version: str
    display_name: str = ""
    capabilities: list[str] = field(default_factory=list)
    default_routes: dict[str, str] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    hooks: dict[str, Callable] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.display_name:
            object.__setattr__(self, "display_name", self.name)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict, excluding non-serializable ``hooks``."""
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "display_name": self.display_name,
            "capabilities": list(self.capabilities),
            "default_routes": dict(self.default_routes),
            "config": dict(self.config),
        }

    def __repr__(self) -> str:
        return f"MemberManifest(id={self.id!r}, name={self.name!r}, version={self.version!r})"
