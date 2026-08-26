from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from precision_gate.cli import run_inputs


def _write_inputs(root: Path, quinta_execution_id: str = "case-001") -> tuple[Path, Path]:
    digest = sha256(b"synthetic evidence").hexdigest()
    tcria_path = root / "tcria.json"
    quinta_path = root / "quinta.json"
    tcria_payload = {
        "accusation_set": [
            {
                "file_name": "synthetic.txt",
                "sha256": digest,
                "extraction_status": "ok",
                "classification": "ACCUSATORY_CANDIDATE",
                "raises_accusation": True,
            }
        ],
        "non_accusation_set": [],
    }
    tcria_path.write_text(json.dumps(tcria_payload), encoding="utf-8")
    tcria_bundle_digest = sha256(
        json.dumps(
            tcria_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    quinta_path.write_text(
        json.dumps(
            {
                "execution_id": quinta_execution_id,
                "status": "conditional",
                "confidence": 0.8,
                "findings": [],
                "remaining_uncertainties": [],
                "human_review_required": True,
                "execution_context_sha256": digest,
                "integration": {
                    "schema_version": "1.0",
                    "tcria_audit_bundle_sha256": tcria_bundle_digest,
                },
            }
        ),
        encoding="utf-8",
    )
    return tcria_path, quinta_path


def test_run_inputs_writes_eight_views_and_markdown_manifest(tmp_path: Path) -> None:
    tcria_path, quinta_path = _write_inputs(tmp_path)

    result = run_inputs(
        execution_id="case-001",
        tcria_path=tcria_path,
        quinta_path=quinta_path,
        output_dir=tmp_path / "out",
    )

    assert result["report_count"] == 8
    manifest = Path(result["manifest"])
    assert manifest.exists()
    assert "precision_summary.md" in manifest.read_text(encoding="utf-8")
    audit_record = Path(result["audit_record"])
    assert audit_record.exists()
    assert json.loads(audit_record.read_text(encoding="utf-8"))["record_sha256"]


def test_run_inputs_rejects_cross_case_mixing(tmp_path: Path) -> None:
    tcria_path, quinta_path = _write_inputs(tmp_path, quinta_execution_id="other-case")

    with pytest.raises(ValueError, match="does not match"):
        run_inputs(
            execution_id="case-001",
            tcria_path=tcria_path,
            quinta_path=quinta_path,
            output_dir=tmp_path / "out",
        )


def test_run_inputs_rejects_tcria_bundle_mixing(tmp_path: Path) -> None:
    tcria_path, quinta_path = _write_inputs(tmp_path)
    payload = json.loads(tcria_path.read_text(encoding="utf-8"))
    payload["accusation_set"][0]["classification"] = "changed"
    tcria_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="does not match"):
        run_inputs(
            execution_id="case-001",
            tcria_path=tcria_path,
            quinta_path=quinta_path,
            output_dir=tmp_path / "out",
        )
