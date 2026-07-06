"""Provider configuration and registry — manages LLM provider definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderConfig:
    """Configuration for a single LLM provider.

    Attributes:
        id: Unique provider identifier.
        kind: Provider kind (e.g. "openai", "anthropic").
        name: Human-readable name.
        base_url: Base URL for the provider API endpoint.
        api_key_ref: Reference string for looking up the API key from a secrets
            store. Must never contain a raw API key value.
        default_model: Default model to use when none is specified.
        models: List of available model identifiers.
        metadata: Arbitrary provider-specific metadata.
        enabled: Whether this provider is active.
    """

    id: str
    kind: str
    name: str
    base_url: str = ""
    api_key_ref: str = ""
    default_model: str = ""
    models: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "base_url": self.base_url,
            "api_key_ref": self.api_key_ref,
            "default_model": self.default_model,
            "models": list(self.models),
            "metadata": dict(self.metadata),
            "enabled": self.enabled,
        }

    def __repr__(self) -> str:
        return (
            f"ProviderConfig(id={self.id!r}, kind={self.kind!r}, "
            f"name={self.name!r}, enabled={self.enabled})"
        )


class ProviderRegistry:
    """Registry of provider configurations — enforces unique provider IDs."""

    def __init__(self) -> None:
        self._providers: dict[str, ProviderConfig] = {}

    def register(self, config: ProviderConfig) -> None:
        """Register a provider configuration.

        Raises:
            ValueError: If a provider with the same id is already registered.
        """
        if config.id in self._providers:
            raise ValueError(f"Provider '{config.id}' is already registered")
        self._providers[config.id] = config

    def get(self, provider_id: str) -> ProviderConfig:
        """Get a provider configuration by id.

        Raises:
            KeyError: If no provider with the given id is registered.
        """
        if provider_id not in self._providers:
            raise KeyError(f"Provider '{provider_id}' not found in registry")
        return self._providers[provider_id]

    def list(self) -> list[ProviderConfig]:
        """List all registered providers, sorted by id."""
        return sorted(self._providers.values(), key=lambda p: p.id)

    def select_default(
        self, kind: str | None = None
    ) -> ProviderConfig:
        """Return the default enabled provider, optionally filtered by kind.

        Prefers providers that have ``default_model`` set.  When *kind* is
        specified, only providers of that kind are considered.

        Raises:
            KeyError: If no matching enabled provider is found.
        """
        candidates = [
            p
            for p in self._providers.values()
            if p.enabled and (kind is None or p.kind == kind)
        ]
        if not candidates:
            msg = "No enabled provider found"
            if kind is not None:
                msg += f" of kind '{kind}'"
            raise KeyError(msg)

        # Prefer providers with an explicit default_model
        candidates.sort(key=lambda p: (0 if p.default_model else 1, p.id))
        return candidates[0]

    def __len__(self) -> int:
        return len(self._providers)

    def __contains__(self, provider_id: str) -> bool:
        return provider_id in self._providers

    def __iter__(self):
        return iter(self.list())


__all__ = [
    "ProviderConfig",
    "ProviderRegistry",
]
