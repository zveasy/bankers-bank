"""SDK shim – forwards everything to canonical bankersbank."""
import importlib, sys
from pathlib import Path

# Compute repository root: sdk/python/bankersbank/__init__.py -> go up 3 dirs to repo root
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))  # ensure canonical package resolves first

_real = importlib.import_module("bankersbank")
sys.modules[__name__].__dict__.update(_real.__dict__)

# The sub-modules are now part of the main package, no need to import separately