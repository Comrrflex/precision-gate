from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from typing import Any

from precision_gate.audit import write_audit_record
from precision_gate.pipeline import PrecisionPipeline
from precision_gate.reporting import write_report_bundle


def run_inputs(
    *,
    execution_id: str,
    tcria_path: str | Path,
    quinta_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    if not isinstance(execution_id, str) or not execution_id.strip():
        raise ValueError("execution_id must be a non-empty string")

    tcria_bundle = _read_object(tcria_path, "TCRIA bundle")
    quinta_decision = _read_object(quinta_path, "Quinta Ordem decision")
    quinta_execution_id = quinta_decision.get("execution_id")
    if quinta_execution_id != execution_id:
        raise ValueError(
            "Quinta Ordem execution_id does not match the requested Precision execution"
        )
    _validate_upstream_digest(tcria_bundle, quinta_decision)

    result = PrecisionPipeline().run(
        execution_id=execution_id,
        tcria_bundle=tcria_bundle,
        quinta_decision=quinta_decision,
    )
    paths = write_report_bundle(result, output_dir)
    audit_record = write_audit_record(result, Path(output_dir) / "precision_audit.json")
    manifest = _write_markdown_manifest(execution_id, paths, Path(output_dir))
    return {
        "execution_id": result.execution_id,
        "report_count": len(paths),
        "manifest": str(manifest),
        "audit_record": str(audit_record),
        "alerts": len(result.alerts),
    }


def _read_object(path: str | Path, label: str) -> dict[str, Any]:
    source = Path(path).expanduser().resolve(strict=True)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise TypeError(f"{label} must be a JSON object")
    return dict(payload)


def _validate_upstream_digest(
    tcria_bundle: Mapping[str, Any],
    quinta_decision: Mapping[str, Any],
) -> None:
    integration = quinta_decision.get("integration")
    if not isinstance(integration, Mapping):
        raise TypeError("Quinta Ordem integration metadata is required")
    expected = integration.get("tcria_audit_bundle_sha256")
    if not _is_sha256(expected):
        raise ValueError("Quinta Ordem TCRIA bundle digest is invalid")
    canonical = json.dumps(
        tcria_bundle,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    actual = sha256(canonical).hexdigest()
    if actual != expected.lower():
        raise ValueError("TCRIA bundle does not match the bundle evaluated by Quinta Ordem")


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _write_markdown_manifest(
    execution_id: str,
    report_paths: tuple[Path, ...],
    output_dir: Path,
) -> Path:
    root = output_dir.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Precision Gate Output Manifest",
        "",
        "> Derived integrity manifest. Original evidence and upstream outputs are not modified.",
        "",
        f"- Execution ID: `{execution_id}`",
        "- Hash algorithm: `SHA-256`",
        "",
        "| Report | Size (bytes) | SHA-256 |",
        "| --- | ---: | --- |",
    ]
    for path in sorted(report_paths, key=lambda item: item.name):
        data = path.read_bytes()
        lines.append(f"| `{path.name}` | {len(data)} | `{sha256(data).hexdigest()}` |")
    lines.append("")
    target = root / "precision_manifest.md"
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="precision-gate",
        description="Run Precision after authoritative TCRIA and Quinta Ordem outputs.",
    )
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--tcria", required=True, help="TCRIA native audit bundle JSON")
    parser.add_argument("--quinta", required=True, help="Quinta Ordem decision JSON")
    parser.add_argument("--output", required=True, help="Derived Markdown output directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_inputs(
        execution_id=args.execution_id,
        tcria_path=args.tcria,
        quinta_path=args.quinta,
        output_dir=args.output,
    )
    print("Precision Gate completed:")
    for key, value in result.items():
        print(f"- {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
