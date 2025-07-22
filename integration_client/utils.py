"""
Shared test utilities for integration-client suite
"""
# simple global list referenced by SDK or mock (import path adjust if needed)
from bankersbank.client import _COLLATERAL_REGISTRY


def clear_collateral_registry() -> None:
    """Reset collateral registry between tests."""
    _COLLATERAL_REGISTRY.clear()
