"""Bankers Bank API Client Package.

This package provides the main API client for interacting with the Bankers Bank system.
"""

# Import main classes for easy access
try:
    from ._client_impl import BankersBankClient, _COLLATERAL_REGISTRY
    from .finastra import FinastraAPIClient, ClientCredentialsTokenProvider, fetch_token

    __all__ = [
        "BankersBankClient",
        "FinastraAPIClient",
        "ClientCredentialsTokenProvider",
        "fetch_token",
        "_COLLATERAL_REGISTRY",
    ]
except ImportError:
    # Handle case where modules might not be fully initialized yet
    __all__ = []
