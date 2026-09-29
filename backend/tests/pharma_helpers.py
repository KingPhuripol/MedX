"""Shared helpers for the s5 Pharma Agent tests (synthetic data only)."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import create_schema
from app.gateway import GatewayRequest, GatewayResponse, build_provider, invoke_gateway
from app.pharma.models import MedSnapshot
from app.pharma.pipeline import reconcile

AS_OF = "2026-06-10T10:00:00+07:00"
BEFORE = "2026-06-10T09:00:00+07:00"
AFTER = "2026-06-10T11:00:00+07:00"
PROV = "synthetic: unit test"


def mem_engine():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    create_schema(engine)
    return engine


def mock_invoke(engine=None, provider=None):
    engine = engine or mem_engine()
    provider = provider or build_provider("mock", Settings())

    def invoke(req: GatewayRequest) -> GatewayResponse:
        return invoke_gateway(engine, provider, req, request_id="test", actor_id=None, actor_role="test")

    return invoke


def source(source_type: str, entries: list, at: str = BEFORE, ref: str | None = None) -> dict:
    return {
        "source_type": source_type,
        "evidence_ref": ref or f"t/{source_type}/1",
        "available_at_time": at,
        "provenance": PROV,
        "version": "1",
        "entries": entries,
    }


def allergy(text: str, at: str = BEFORE, ref: str = "t/allergy/1") -> dict:
    return {"text": text, "evidence_ref": ref, "available_at_time": at, "provenance": PROV, "version": "1"}


def snapshot(home=None, reported=None, orders=None, allergies=(), data_class="synthetic", extra_sources=()) -> MedSnapshot:
    sources = []
    if home is not None:
        sources.append(source("home_list", home))
    if reported is not None:
        sources.append(source("patient_reported", reported))
    if orders is not None:
        sources.append(source("new_order", orders))
    sources.extend(extra_sources)
    return MedSnapshot.model_validate({
        "patient_ref": "t-patient-1",
        "as_of": AS_OF,
        "data_class": data_class,
        "sources": sources,
        "allergies": [a if isinstance(a, dict) else allergy(a, ref=f"t/allergy/{n}") for n, a in enumerate(allergies)],
    })


def run(snap: MedSnapshot, mode: str = "rules_plus_model", invoke=None) -> dict:
    return reconcile(snap, invoke or mock_invoke(), mode)


def of_type(run_result: dict, kind: str) -> list[dict]:
    return [i for i in run_result["issues"] if i["type"] == kind]


def notices(run_result: dict, kind: str) -> list[dict]:
    return [n for n in run_result["notices"] if n["type"] == kind]
