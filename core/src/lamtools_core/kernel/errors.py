"""Kernel error types."""

from __future__ import annotations


class KernelError(Exception):
    """Base error for Core Loop Kernel operations."""


class ModelCallError(KernelError):
    """LLM model call failed after retries."""


class TokenOverflowError(KernelError):
    """Request exceeded model context window. Not retryable — the request
    must be compacted or shortened before retrying."""


class RateLimitError(KernelError):
    """Provider returned a rate-limit error (HTTP 429). Should honor
    Retry-After header if available."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class StateSaveError(KernelError):
    """Failed to save runtime state."""


__all__ = [
    "KernelError",
    "ModelCallError",
    "TokenOverflowError",
    "RateLimitError",
    "StateSaveError",
]
