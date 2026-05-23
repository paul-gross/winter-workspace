from __future__ import annotations

from typing import Any


def deep_merge(base: dict, overlay: dict) -> dict:
    """Deep-merge overlay onto base. Overlay scalar keys win; dicts recurse; lists concatenate.

    List concatenation matters for workspace config: it lets `config.local.toml`
    add `[[project_repository]]` / `[[standalone_repository]]` entries without
    wiping the shared set declared in `config.toml`.
    """
    if not overlay:
        return dict(base)
    result: dict[str, Any] = dict(base)
    for key, value in overlay.items():
        existing = result.get(key)
        if isinstance(value, dict) and isinstance(existing, dict):
            result[key] = deep_merge(existing, value)
        elif isinstance(value, list) and isinstance(existing, list):
            result[key] = existing + value
        else:
            result[key] = value
    return result
