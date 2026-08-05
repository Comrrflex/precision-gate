from pathlib import Path

from precision_gate import PrecisionPipeline, write_report_bundle

bundle = {
    "accusation_set": [],
    "non_accusation_set": [
        {
            "file_name": "synthetic_case.md",
            "sha256": "0" * 64,
            "extraction_status": "ok",
            "classification": "fact_supported",
            "information_state": "fact_supported",
            "evidence_refs": ["EVD-SYNTHETIC-001"],
            "summary": "Synthetic fact used only to demonstrate the integration contract.",
        }
    ],
}

api_outputs = [
    {
        "output_id": "api-synthesis-1",
        "kind": "synthesis",
        "content": "A model-generated synthesis that remains classified as inference.",
        "support_refs": ["EVD-SYNTHETIC-001"],
        "requires_human_review": True,
    }
]

result = PrecisionPipeline().run(
    execution_id="precision-demo-1",
    tcria_bundle=bundle,
    api_outputs=api_outputs,
)

for path in write_report_bundle(result, Path("outputs")):
    print(path)
