from __future__ import annotations

import json
import os
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Any

from precision_gate.pipeline import PipelineResult

AUDIT_SCHEMA_VERSION = "1.0"
GENESIS_HASH = "0" * 64


def canonical_sha256(value: object) -> str:
    """Return the SHA-256 of a stable UTF-8 JSON representation."""
    return sha256(_canonical_json(value)).hexdigest()


def build_audit_record(result: PipelineResult) -> dict[str, Any]:
    """Build a deterministic, tamper-evident record for one run."""
    previous_hash = GENESIS_HASH
    entries: list[dict[str, Any]] = []
    for sequence, event in enumerate(result.events, start=1):
        payload = asdict(event)
        payload["information_state"] = event.information_state.value
        payload["custody_state"] = event.custody_state.value
        event_hash = canonical_sha256(
            {"sequence": sequence, "previous_hash": previous_hash, "event": payload}
        )
        entries.append({
            "sequence": sequence,
            "previous_hash": previous_hash,
            "event_hash": event_hash,
            "event": payload,
        })
        previous_hash = event_hash

    context = result.upstream_context
    record: dict[str, Any] = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "execution_id": result.execution_id,
        "flow": context["flow"],
        "flow_complete": context["flow_complete"],
        "upstream": {
            "tcria_bundle_sha256": canonical_sha256(context["tcria_bundle"]),
            "quinta_decision_sha256": (
                canonical_sha256(context["quinta_decision"])
                if context["quinta_decision"] is not None
                else None
            ),
            "api_output_count": context["api_output_count"],
        },
        "metrics": result.metrics.as_dict(),
        "alerts": list(result.alerts),
        "events": entries,
        "chain_head_sha256": previous_hash,
    }
    record["record_sha256"] = canonical_sha256(record)
    return record


def verify_audit_record(record: dict[str, Any]) -> bool:
    """Verify the record digest and every event-chain link."""
    supplied_digest = record.get("record_sha256")
    unsigned = {key: value for key, value in record.items() if key != "record_sha256"}
    if supplied_digest != canonical_sha256(unsigned):
        return False

    previous_hash = GENESIS_HASH
    events = record.get("events")
    if not isinstance(events, list):
        return False
    for sequence, entry in enumerate(events, start=1):
        if not isinstance(entry, dict) or entry.get("sequence") != sequence:
            return False
        if entry.get("previous_hash") != previous_hash:
            return False
        expected = canonical_sha256(
            {"sequence": sequence, "previous_hash": previous_hash, "event": entry.get("event")}
        )
        if entry.get("event_hash") != expected:
            return False
        previous_hash = expected
    return record.get("chain_head_sha256") == previous_hash


def write_audit_record(result: PipelineResult, path: str | Path) -> Path:
    """Atomically write the machine-readable audit record."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(build_audit_record(result), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return target


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
