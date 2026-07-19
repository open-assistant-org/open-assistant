"""Helpers for interpreting settings values."""

from typing import Any


def settings_truthy(val: Any) -> bool:
    """Return whether a settings value should be treated as enabled/truthy.

    Settings may be stored as a real bool (``value_type='bool'`` rows) or, for
    legacy rows written before typed storage, as the strings ``'true'``/``'false'``.
    ``None`` and any other value are treated as disabled.
    """
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    return str(val).lower() == "true"
