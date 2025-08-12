"""Shared helpers for integration tests."""

from bankersbank.client import _COLLATERAL_REGISTRY


def clear_collateral_registry() -> None:
    """Reset global collateral registry between tests."""
    _COLLATERAL_REGISTRY.clear()
