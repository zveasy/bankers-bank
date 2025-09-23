"""SDK shim forwarding to canonical bankersbank.client."""
from importlib import import_module as _imp
globals().update(_imp("bankersbank.client").__dict__)
