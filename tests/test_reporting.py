from precision_gate.pipeline import PrecisionPipeline
from precision_gate.reporting import REPORT_FILENAMES, render_markdown, write_report_bundle


def _result(sign_api_output):
    return PrecisionPipeline().run(
        execution_id="report-1",
        tcria_bundle={
            "accusation_set": [],
            "non_accusation_set": [
                {
                    "file_name": "fixture.md",
                    "sha256": "2" * 64,
                    "extraction_status": "ok",
                    "classification": "signal",
                    "summary": "Synthetic fixture signal.",
                }
            ],
        },
        api_outputs=[
            sign_api_output({
                "output_id": "api-report",
                "content": "Synthetic inferred reading.",
                "kind": "inference",
                "support_refs": ["fixture.md"],
                "requires_human_review": True,
            })
        ],
    )


def test_consolidated_report_contains_custody_notice(sign_api_output) -> None:
    report = render_markdown(_result(sign_api_output))

    assert "Derived analytical artifact" in report
    assert "Final authority remains human" in report
    assert "AI/API inferences and opinions" in report


def test_report_bundle_writes_eight_markdown_files(tmp_path, sign_api_output) -> None:
    paths = write_report_bundle(_result(sign_api_output), tmp_path)

    assert tuple(path.name for path in paths) == REPORT_FILENAMES
    assert len(paths) == 8
    assert all(path.suffix == ".md" for path in paths)
    assert all(path.exists() for path in paths)
