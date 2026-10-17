"""Plain-assert smoke test for the multi-agent ingestion pipeline (no pytest).

Forces LLM_PROVIDER=mock so this runs with no API key. Covers:
  (a) build_case_operations() against the section-3 case -> operations table,
      for all 9 LifecycleCase values, on hand-built ExtractionResult/ValidationReport
      fixtures.
  (b) An end-to-end ingest of sample_docs/examples with sample_docs/seed_corpus.json
      loaded, checking both feedback loops fired and the final storage snapshot.

Run: python smoke_test.py
See .omc/plans/autopilot-impl.md section 6, Unit E, item 5.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Must be set before Settings.from_env() is ever called.
os.environ["LLM_PROVIDER"] = "mock"

from config import Settings  # noqa: E402
from llm_provider import get_provider  # noqa: E402
from logging_trace import InteractionLogger  # noqa: E402
from pipeline import IngestionPipeline  # noqa: E402
from schema import (  # noqa: E402
    DocumentMetadata,
    ExtractionResult,
    IdentityMetadata,
    LifecycleCase,
    LifecycleMetadata,
    LineageMetadata,
    PatchRecord,
    StoredDocument,
    TermDefinition,
    ValidationReport,
)
from storage import InMemoryStorage  # noqa: E402
from agents.graph_update import build_case_operations  # noqa: E402

ROOT = Path(__file__).resolve().parent
FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"ok: {message}")
    else:
        FAILURES.append(message)
        print(f"FAIL: {message}")


# ---------------------------------------------------------------------------
# (a) build_case_operations() vs. the section 3 table
# ---------------------------------------------------------------------------

NEW_ID = "N-DOC-2024"
T1 = "T-ONE-2020"
T2 = "T-TWO-2021"


def _meta(
    doc_id: str,
    *,
    doc_type: str = "resolucion",
    lifecycle: LifecycleMetadata | None = None,
) -> DocumentMetadata:
    return DocumentMetadata(
        identity_metadata=IdentityMetadata(doc_id=doc_id, doc_type=doc_type),
        lifecycle_metadata=lifecycle or LifecycleMetadata(),
        lineage_metadata=LineageMetadata(),
    )


def _extraction(**kwargs) -> ExtractionResult:
    metadata = kwargs.pop("metadata", None) or _meta(NEW_ID)
    return ExtractionResult(metadata=metadata, **kwargs)


def _report(resolved_refs=None, missing_refs=None, **kwargs) -> ValidationReport:
    return ValidationReport(
        ok=kwargs.pop("ok", True),
        resolved_refs=resolved_refs or {},
        missing_refs=missing_refs or [],
        recommendation=kwargs.pop("recommendation", "proceed"),
        **kwargs,
    )


def _stored_from_create(ops) -> StoredDocument:
    create_ops = [o for o in ops if o.op == "create_document"]
    check(len(create_ops) == 1, "exactly one create_document op, for N")
    return StoredDocument.model_validate(create_ops[0].value)


def _target_ops(ops, doc_id: str):
    return [o for o in ops if o.doc_id == doc_id and o.op != "create_document"]


def _find(ops, op: str, doc_id: str, field=None):
    for o in ops:
        if o.op == op and o.doc_id == doc_id and (field is None or o.field == field):
            return o
    return None


def test_case_1_new_statement() -> None:
    ext = _extraction()
    rep = _report()
    ops = build_case_operations(LifecycleCase.NEW_STATEMENT, ext, rep, NEW_ID, "raw text")
    stored = _stored_from_create(ops)
    check(stored.metadata.doc_id == NEW_ID, "case 1 NEW_STATEMENT: N has the right doc_id")
    check(len(ops) == 1, "case 1 NEW_STATEMENT: create only, no target ops")


def test_case_2_full_replacement() -> None:
    ext = _extraction(effective_date="2024-01-01", target_doc_ids=[T1])
    rep = _report(resolved_refs={"ref": T1})
    ops = build_case_operations(LifecycleCase.FULL_REPLACEMENT, ext, rep, NEW_ID, "raw text")
    stored = _stored_from_create(ops)
    check(stored.metadata.lineage_metadata.supersedes == [T1], "case 2: N.lineage.supersedes = T")
    t_ops = _target_ops(ops, T1)
    status_op = _find(t_ops, "set_status", T1)
    check(
        status_op is not None and status_op.value.get("status") == "SUPERSEDED",
        "case 2: target set_status SUPERSEDED",
    )
    check(
        status_op is not None and status_op.value.get("valid_until") == "2024-01-01",
        "case 2: target valid_until = effective_date",
    )
    lineage_op = _find(t_ops, "append_lineage", T1, field="superseded_by")
    check(
        lineage_op is not None and lineage_op.value == NEW_ID,
        "case 2: target append_lineage superseded_by N",
    )


def test_case_3_replacement_with_contradiction() -> None:
    # total contradiction
    ext = _extraction(
        effective_date="2024-01-01",
        target_doc_ids=[T1],
        contradiction_scope="total",
        contradiction_notes=["nota de contradiccion"],
    )
    rep = _report(resolved_refs={"ref": T1})
    ops = build_case_operations(
        LifecycleCase.REPLACEMENT_WITH_CONTRADICTION, ext, rep, NEW_ID, "raw text"
    )
    stored = _stored_from_create(ops)
    check(stored.metadata.lineage_metadata.supersedes == [T1], "case 3 (total): N.lineage.supersedes = T")
    check(stored.metadata.lineage_metadata.contradicts == [T1], "case 3 (total): N.lineage.contradicts = T")
    check(
        "nota de contradiccion" in stored.metadata.lifecycle_metadata.notes,
        "case 3 (total): N.lifecycle.notes += contradiction_notes",
    )
    check(
        "CONTRADICTION" in stored.metadata.lifecycle_metadata.review_flags,
        "case 3 (total): N gets flag CONTRADICTION",
    )
    t_ops = _target_ops(ops, T1)
    status_op = _find(t_ops, "set_status", T1)
    check(
        status_op is not None and status_op.value.get("status") == "SUPERSEDED"
        and status_op.value.get("valid_until") == "2024-01-01",
        "case 3 (total): target SUPERSEDED with valid_until",
    )
    check(
        _find(t_ops, "append_lineage", T1, field="superseded_by") is not None,
        "case 3 (total): target append_lineage superseded_by N",
    )
    flag_op = _find(t_ops, "add_review_flag", T1)
    check(
        flag_op is not None and flag_op.value == f"CONTRADICTED_BY:{NEW_ID}",
        "case 3 (total): target gets flag CONTRADICTED_BY:N",
    )

    # partial contradiction
    ext_p = _extraction(
        effective_date="2024-01-01",
        target_doc_ids=[T1],
        contradiction_scope="partial",
        contradiction_notes=["nota parcial"],
    )
    rep_p = _report(resolved_refs={"ref": T1})
    ops_p = build_case_operations(
        LifecycleCase.REPLACEMENT_WITH_CONTRADICTION, ext_p, rep_p, NEW_ID, "raw text"
    )
    t_ops_p = _target_ops(ops_p, T1)
    status_op_p = _find(t_ops_p, "set_status", T1)
    check(
        status_op_p is not None and status_op_p.value.get("status") == "PARTIALLY_SUPERSEDED",
        "case 3 (partial): target PARTIALLY_SUPERSEDED",
    )
    check(
        status_op_p is not None and not status_op_p.value.get("valid_until"),
        "case 3 (partial): no valid_until set on target",
    )


def test_case_4_revocation_or_expiration() -> None:
    # revocation
    ext = _extraction(effective_date="2024-01-01", target_doc_ids=[T1], revocation_kind="revocation")
    rep = _report(resolved_refs={"ref": T1})
    ops = build_case_operations(LifecycleCase.REVOCATION_OR_EXPIRATION, ext, rep, NEW_ID, "raw text")
    stored = _stored_from_create(ops)
    check(stored.metadata.lineage_metadata.revokes == [T1], "case 4 (revocation): N.lineage.revokes = T")
    t_ops = _target_ops(ops, T1)
    status_op = _find(t_ops, "set_status", T1)
    check(
        status_op is not None and status_op.value.get("status") == "REVOKED"
        and status_op.value.get("valid_until") == "2024-01-01",
        "case 4 (revocation): target set_status REVOKED with valid_until",
    )
    check(
        _find(t_ops, "append_lineage", T1, field="revoked_by") is not None,
        "case 4 (revocation): target append_lineage revoked_by N",
    )

    # expiration
    ext_e = _extraction(effective_date="2024-01-01", target_doc_ids=[T1], revocation_kind="expiration")
    rep_e = _report(resolved_refs={"ref": T1})
    ops_e = build_case_operations(LifecycleCase.REVOCATION_OR_EXPIRATION, ext_e, rep_e, NEW_ID, "raw text")
    t_ops_e = _target_ops(ops_e, T1)
    status_op_e = _find(t_ops_e, "set_status", T1)
    check(
        status_op_e is not None and status_op_e.value.get("status") == "EXPIRED",
        "case 4 (expiration): target set_status EXPIRED",
    )


def test_case_5_consolidation() -> None:
    ext = _extraction(effective_date="2024-01-01", target_doc_ids=[T1, T2])
    rep = _report(resolved_refs={"r1": T1, "r2": T2})
    ops = build_case_operations(LifecycleCase.CONSOLIDATION, ext, rep, NEW_ID, "raw text")
    stored = _stored_from_create(ops)
    check(
        set(stored.metadata.lineage_metadata.consolidates) == {T1, T2},
        "case 5: N.lineage.consolidates = T (both sources)",
    )
    for t in (T1, T2):
        t_ops = _target_ops(ops, t)
        status_op = _find(t_ops, "set_status", t)
        check(
            status_op is not None and status_op.value.get("status") == "SUPERSEDED"
            and status_op.value.get("valid_until") == "2024-01-01",
            f"case 5: target {t} SUPERSEDED with valid_until",
        )
        check(
            _find(t_ops, "append_lineage", t, field="superseded_by") is not None,
            f"case 5: target {t} append_lineage superseded_by N",
        )


def test_case_6_splitting() -> None:
    ext = _extraction(effective_date="2024-01-01", target_doc_ids=[T1])
    rep = _report(resolved_refs={"ref": T1})
    ops = build_case_operations(LifecycleCase.SPLITTING, ext, rep, NEW_ID, "raw text")
    stored = _stored_from_create(ops)
    check(stored.metadata.lineage_metadata.split_from == [T1], "case 6: N.lineage.split_from = T")
    t_ops = _target_ops(ops, T1)
    status_op = _find(t_ops, "set_status", T1)
    check(
        status_op is not None and status_op.value.get("status") == "SUPERSEDED"
        and status_op.value.get("valid_until") == "2024-01-01",
        "case 6: target SUPERSEDED with valid_until",
    )
    check(
        _find(t_ops, "append_lineage", T1, field="split_into") is not None,
        "case 6: target append_lineage split_into N",
    )
    check(
        _find(t_ops, "append_lineage", T1, field="superseded_by") is not None,
        "case 6: target append_lineage superseded_by N",
    )


def test_case_7_patch_erratum() -> None:
    patch = PatchRecord(clause="Articulo 5", old_text="treinta (30) dias", new_text="quince (15) dias")
    ext = _extraction(effective_date="2024-01-01", target_doc_ids=[T1], patches=[patch])
    rep = _report(resolved_refs={"ref": T1})
    ops = build_case_operations(LifecycleCase.PATCH_ERRATUM, ext, rep, NEW_ID, "raw text")
    stored = _stored_from_create(ops)
    check(stored.metadata.lineage_metadata.amends == [T1], "case 7: N.lineage.amends = T")
    check(
        stored.metadata.identity_metadata.doc_type == "fe_de_erratas",
        "case 7: N.identity.doc_type = fe_de_erratas",
    )
    t_ops = _target_ops(ops, T1)
    patch_op = _find(t_ops, "append_patch", T1)
    check(patch_op is not None, "case 7: target has an append_patch op")
    if patch_op is not None:
        applied = PatchRecord.model_validate(patch_op.value)
        check(applied.clause == "Articulo 5", "case 7: patch clause preserved")
        check(applied.patched_by == NEW_ID, "case 7: patch.patched_by = N")
        check(applied.effective_date == "2024-01-01", "case 7: patch.effective_date = d")


def test_case_8_temporary_exception() -> None:
    lifecycle = LifecycleMetadata(valid_from="2024-01-01", valid_until="2024-06-01")
    ext = _extraction(metadata=_meta(NEW_ID, lifecycle=lifecycle), target_doc_ids=[T1])
    rep = _report(resolved_refs={"ref": T1})
    ops = build_case_operations(LifecycleCase.TEMPORARY_EXCEPTION, ext, rep, NEW_ID, "raw text")
    stored = _stored_from_create(ops)
    check(stored.metadata.lineage_metadata.overrides == [T1], "case 8: N.lineage.overrides = T")
    check(
        stored.metadata.lifecycle_metadata.valid_from == "2024-01-01"
        and stored.metadata.lifecycle_metadata.valid_until == "2024-06-01",
        "case 8: N keeps valid_from/valid_until",
    )
    check(
        "MISSING_EXPIRY" not in stored.metadata.lifecycle_metadata.review_flags,
        "case 8: no MISSING_EXPIRY flag when valid_until is present",
    )
    t_ops = _target_ops(ops, T1)
    check(
        _find(t_ops, "append_lineage", T1, field="overridden_by") is not None,
        "case 8: target append_lineage overridden_by N",
    )
    flag_op = _find(t_ops, "add_review_flag", T1)
    check(
        flag_op is not None and flag_op.value == f"TEMP_EXCEPTION:{NEW_ID}:2024-01-01..2024-06-01",
        "case 8: target gets flag TEMP_EXCEPTION:N:<from>..<until>",
    )

    # missing valid_until -> MISSING_EXPIRY flag on N
    lifecycle_no_until = LifecycleMetadata(valid_from="2024-01-01", valid_until=None)
    ext2 = _extraction(metadata=_meta(NEW_ID, lifecycle=lifecycle_no_until), target_doc_ids=[T1])
    rep2 = _report(resolved_refs={"ref": T1})
    ops2 = build_case_operations(LifecycleCase.TEMPORARY_EXCEPTION, ext2, rep2, NEW_ID, "raw text")
    stored2 = _stored_from_create(ops2)
    check(
        "MISSING_EXPIRY" in stored2.metadata.lifecycle_metadata.review_flags,
        "case 8: MISSING_EXPIRY flag added to N when valid_until is absent",
    )


def test_case_9_indirect_dependency_update() -> None:
    term = TermDefinition(term="cliente vulnerable", definition="nueva definicion de prueba")
    ext = _extraction(redefined_terms=[term])
    rep = _report()
    ops = build_case_operations(LifecycleCase.INDIRECT_DEPENDENCY_UPDATE, ext, rep, NEW_ID, "raw text")
    stored = _stored_from_create(ops)
    check(
        "cliente vulnerable" in stored.metadata.identity_metadata.defined_terms,
        "case 9: N.identity.defined_terms += redefined term(s)",
    )
    # Per the table's "(via loop 2, per affected doc A)" annotation,
    # set_definition_source(A, term, N) is emitted by build_impact_operations
    # once an affected document A is found and reassessed -- not here, since
    # build_case_operations has no knowledge of A yet. Covered below.
    check(
        _find(ops, "set_definition_source", NEW_ID) is None,
        "case 9: no set_definition_source op on N itself from build_case_operations "
        "(deferred to loop 2 / build_impact_operations per affected doc)",
    )


def test_case_9_build_impact_operations() -> None:
    from agents.graph_update import build_impact_operations
    from schema import ImpactAssessment, ReinvocationRequest, TermUsage

    request = ReinvocationRequest(
        source_doc_id=NEW_ID,
        target_doc_id=T1,
        term="cliente vulnerable",
        new_definition="nueva definicion de prueba",
    )

    # not affected -> no ops
    not_affected = ImpactAssessment(target_doc_id=T1, term="cliente vulnerable", affected=False)
    check(
        build_impact_operations(request, not_affected, None) == [],
        "case 9 impact: no ops when assessment.affected is False",
    )

    # affected -> set_definition_source(A, term, N) + flag + append_lineage impacts on N
    affected = ImpactAssessment(target_doc_id=T1, term="cliente vulnerable", affected=True)
    usage = TermUsage(target_doc_id=T1, term="cliente vulnerable", clauses=["clausula de ejemplo"])
    ops = build_impact_operations(request, affected, usage)
    def_op = _find(ops, "set_definition_source", T1, field="cliente vulnerable")
    check(
        def_op is not None and def_op.value == NEW_ID,
        "case 9 impact: set_definition_source(A, term, N)",
    )
    flag_op = _find(ops, "add_review_flag", T1)
    check(
        flag_op is not None and flag_op.value == f"TERM_REDEFINED:cliente vulnerable:{NEW_ID}",
        "case 9 impact: target gets flag TERM_REDEFINED:<term>:N",
    )
    impacts_op = _find(ops, "append_lineage", NEW_ID, field="impacts")
    check(
        impacts_op is not None and impacts_op.value == T1,
        "case 9 impact: N.lineage.impacts += A (append_lineage impacts A on N)",
    )


def test_missing_dependency_flag_every_case() -> None:
    ext = _extraction()
    rep = _report(missing_refs=["SBS-RES-9999-2010"])
    ops = build_case_operations(LifecycleCase.NEW_STATEMENT, ext, rep, NEW_ID, "raw text")
    stored = _stored_from_create(ops)
    check(
        stored.metadata.lifecycle_metadata.missing_dependencies == ["SBS-RES-9999-2010"],
        "missing_refs -> N.lifecycle.missing_dependencies (holds for every case)",
    )
    check(
        "MISSING_DEPENDENCY" in stored.metadata.lifecycle_metadata.review_flags,
        "missing_refs -> N gets flag MISSING_DEPENDENCY (holds for every case)",
    )


def test_case_operations() -> None:
    test_case_1_new_statement()
    test_case_2_full_replacement()
    test_case_3_replacement_with_contradiction()
    test_case_4_revocation_or_expiration()
    test_case_5_consolidation()
    test_case_6_splitting()
    test_case_7_patch_erratum()
    test_case_8_temporary_exception()
    test_case_9_indirect_dependency_update()
    test_case_9_build_impact_operations()
    test_missing_dependency_flag_every_case()


# ---------------------------------------------------------------------------
# (b) end-to-end ingest of sample_docs/examples with the seed corpus
# ---------------------------------------------------------------------------


def test_ingest_examples() -> None:
    settings = Settings.from_env(runs_dir=ROOT / "runs" / "_smoke_test")
    provider = get_provider(settings)
    storage = InMemoryStorage.from_seed_file(ROOT / "sample_docs" / "seed_corpus.json")
    logger = InteractionLogger(settings.runs_dir)
    pipeline = IngestionPipeline(storage, provider, logger, settings)

    results = None
    error: Exception | None = None
    try:
        results = pipeline.ingest_path(ROOT / "sample_docs" / "examples")
    except Exception as exc:  # noqa: BLE001 - we want to report any exception, not just ours
        error = exc
    finally:
        logger.close()

    check(error is None, f"ingest_path raised no exception (got: {error!r})")
    if results is None:
        return

    check(len(results) > 0, "ingest_path processed at least one document")
    check(
        all(r.final_case is not None for r in results),
        "every result has a non-None final_case",
    )

    log_path = logger.log_path
    check(log_path.exists(), f"log file exists at {log_path}")

    lines = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    entries = []
    parse_ok = True
    for ln in lines:
        try:
            entries.append(json.loads(ln))
        except json.JSONDecodeError:
            parse_ok = False
    check(parse_ok, "every log line is valid JSON")

    seqs = [e["seq"] for e in entries]
    check(
        seqs == sorted(seqs) and len(seqs) == len(set(seqs)),
        "seq strictly increases across the log",
    )

    loop1_rows = [
        e for e in entries if e.get("event") == "feedback" and e.get("loop") == "validation_to_classifier"
    ]
    check(len(loop1_rows) >= 1, "at least 1 feedback row with loop=validation_to_classifier")

    loop2_rows = [
        e for e in entries if e.get("event") == "feedback" and e.get("loop") == "graph_update_reinvoke"
    ]
    check(len(loop2_rows) >= 1, "at least 1 feedback row with loop=graph_update_reinvoke")

    snapshot = storage.snapshot()
    sbs_2000 = snapshot.get("SBS-RES-2000-2021")
    check(
        sbs_2000 is not None
        and sbs_2000["metadata"]["lifecycle_metadata"]["status"] == "SUPERSEDED",
        "SBS-RES-2000-2021 is SUPERSEDED in the final snapshot",
    )
    sbs_2001 = snapshot.get("SBS-RES-2001-2021")
    check(
        sbs_2001 is not None
        and len(sbs_2001["metadata"]["lifecycle_metadata"]["patch_log"]) > 0,
        "SBS-RES-2001-2021.patch_log is non-empty in the final snapshot",
    )


def main() -> int:
    print("=== (a) build_case_operations vs. section 3 table ===")
    test_case_operations()
    print("\n=== (b) ingest sample_docs/examples with the seed corpus ===")
    test_ingest_examples()

    print()
    if FAILURES:
        print(f"FAIL ({len(FAILURES)} failure(s)):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
