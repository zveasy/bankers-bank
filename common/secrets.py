import json
import os
from pathlib import Path
from typing import Any, Optional


class SecretsManager:
    """Load secrets from a JSON file pointed to by ``SECRETS_PATH``.

    The file is cached on first access. Tests may override or update the
    in-memory cache via :meth:`set_override` or :meth:`update`.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(
            path or os.getenv("SECRETS_PATH", "/var/run/secrets/app.json")
        )
        self._cache: dict[str, Any] | None = None

    def _load(self) -> dict[str, Any]:
        if self._cache is None:
            try:
                with self._path.open("r", encoding="utf-8") as fh:
                    self._cache = json.load(fh)
            except FileNotFoundError:
                self._cache = {}
        return self._cache

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        """Return secret value for *key* or *default* if missing."""

        return self._load().get(key, default)

    def set_override(self, data: dict[str, Any]) -> None:
        """Replace the entire secret cache (test helper)."""

        self._cache = dict(data)

    def update(self, data: dict[str, Any]) -> None:
        """Merge *data* into the existing cache (test helper)."""

        current = self._load()
        current.update(data)
        self._cache = current


# Global default manager
secrets = SecretsManager()


def get_secret(key: str, default: Optional[Any] = None) -> Any:
    """Convenience wrapper around :class:`SecretsManager`."""

    return secrets.get(key, default)
