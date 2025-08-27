"""Finastra integration package (Sprint 11)."""
import os
from typing import Final

BASE_URL: Final[str] = os.getenv("FINASTRA_BASE_URL", "https://api.fusionfabric.cloud")
TENANT: Final[str] = os.getenv("FINASTRA_TENANT", "sandbox")
PRODUCT_COLLATERAL: Final[str] = os.getenv("FINASTRA_PRODUCT_COLLATERAL", "total-lending-collaterals-b2b-v2")
