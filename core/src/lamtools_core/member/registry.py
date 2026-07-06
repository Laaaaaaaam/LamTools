"""Member registry — manages collection of member manifests."""

from __future__ import annotations

from .manifest import MemberManifest


class MemberRegistry:
    """Registry of member manifests — enforces unique member IDs."""

    def __init__(self) -> None:
        self._members: dict[str, MemberManifest] = {}

    def register(self, manifest: MemberManifest) -> None:
        """Register a member manifest.

        Raises:
            ValueError: If a member with the same id is already registered.
        """
        if manifest.id in self._members:
            raise ValueError(f"Member '{manifest.id}' is already registered")
        self._members[manifest.id] = manifest

    def get(self, member_id: str) -> MemberManifest:
        """Get a member manifest by id.

        Raises:
            KeyError: If no member with the given id is registered.
        """
        if member_id not in self._members:
            raise KeyError(f"Member '{member_id}' not found in registry")
        return self._members[member_id]

    def list(self) -> list[MemberManifest]:
        """List all registered member manifests, sorted by id."""
        return sorted(self._members.values(), key=lambda m: m.id)

    def __len__(self) -> int:
        return len(self._members)

    def __contains__(self, member_id: str) -> bool:
        return member_id in self._members

    def __iter__(self):
        return iter(self.list())
