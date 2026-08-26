from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from precision_gate.audit import build_audit_record
from precision_gate.pipeline import PrecisionPipeline
from precision_gate.reporting import render_report_bundle

app = FastAPI(title="Precision Gate API", version="0.1.0")
pipeline = PrecisionPipeline()


class PrecisionRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_id: str = Field(min_length=1)
    tcria_bundle: dict[str, Any]
    quinta_decision: dict[str, Any]
    api_outputs: list[dict[str, Any]] = Field(default_factory=list)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "product": "precision-gate"}


@app.get("/capabilities")
def capabilities() -> dict[str, object]:
    return {
        "product": "precision-gate",
        "authoritative_input_order": ["tcria", "quinta_ordem", "precision"],
        "endpoints": ["health", "capabilities", "run"],
        "markdown_outputs": 8,
        "final_authority": "human",
    }


@app.post("/run")
def run_precision(payload: PrecisionRunRequest) -> dict[str, object]:
    try:
        result = pipeline.run(
            execution_id=payload.execution_id,
            tcria_bundle=payload.tcria_bundle,
            quinta_decision=payload.quinta_decision,
            api_outputs=payload.api_outputs,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "execution_id": result.execution_id,
        "flow": result.upstream_context["flow"],
        "alerts": list(result.alerts),
        "audit_record": build_audit_record(result),
        "markdown_reports": render_report_bundle(result),
    }
