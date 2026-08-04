from __future__ import annotations

import json
from collections.abc import Mapping
from hashlib import sha256
from typing import Any

from precision_gate.contracts import ContractError, canonical_json


def strict_snapshot(payload: Mapping[str, Any], *, name: str) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ContractError(f"{name} must be a mapping.")
    serialized = canonical_json(payload)
    snapshot = json.loads(serialized)
    if not isinstance(snapshot, dict):  # pragma: no cover - mapping invariant
        raise ContractError(f"{name} must serialize to an object.")
    return snapshot


def canonical_sha256(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def require_mapping(payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    if key not in payload:
        raise ContractError(f"{key} is required.")
    value = payload[key]
    if not isinstance(value, Mapping):
        raise ContractError(f"{key} must be a mapping.")
    return dict(value)


def optional_mapping(payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key, {})
    if not isinstance(value, Mapping):
        raise ContractError(f"{key} must be a mapping.")
    return dict(value)


def require_mapping_list(payload: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    if key not in payload:
        raise ContractError(f"{key} is required.")
    value = payload[key]
    if not isinstance(value, list):
        raise ContractError(f"{key} must be a list.")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ContractError(f"{key}[{index}] must be a mapping.")
        result.append(dict(item))
    return result


def require_text(payload: Mapping[str, Any], key: str) -> str:
    if key not in payload:
        raise ContractError(f"{key} is required.")
    value = payload[key]
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{key} must be a non-empty string.")
    return value.strip()


def optional_text(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{key} must be a non-empty string when provided.")
    return value.strip()


def require_bool(payload: Mapping[str, Any], key: str) -> bool:
    if key not in payload:
        raise ContractError(f"{key} is required.")
    value = payload[key]
    if not isinstance(value, bool):
        raise ContractError(f"{key} must be a boolean.")
    return value


def require_non_negative_int(payload: Mapping[str, Any], key: str) -> int:
    if key not in payload:
        raise ContractError(f"{key} is required.")
    value = payload[key]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ContractError(f"{key} must be a non-negative integer.")
    return value


def require_string_list(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    if key not in payload:
        raise ContractError(f"{key} is required.")
    value = payload[key]
    if not isinstance(value, list):
        raise ContractError(f"{key} must be a list.")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ContractError(f"{key}[{index}] must be a non-empty string.")
        result.append(item.strip())
    if len(set(result)) != len(result):
        raise ContractError(f"{key} must not contain duplicates.")
    return tuple(result)
