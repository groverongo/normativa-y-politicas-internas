"""Graph-Update: deterministic case -> metadata-operations table (pure
functions) plus the GraphUpdateAgent that plans, applies, and drives the
case-9 impact re-invocation (loop 2).

`build_case_operations` implements the authoritative table in
.omc/plans/autopilot-impl.md section 3 EXACTLY. Design choice (documented
here since the table leaves some representational freedom): every field the
table lists under "Ops on N (new)" is baked directly into the single
`create_document` operation's `StoredDocument` value -- the table itself says
"The value is the StoredDocument with lineage fields rewritten to resolved
ids", and N does not exist in storage yet so there is nothing to mutate
incrementally. Everything the table lists under "Ops on each t in T" mutates
an *existing* document and is therefore emitted as its own `GraphOperation`
(`set_status` / `append_lineage` / `append_patch` / `add_review_flag`), since
`StorageInterface.apply_operation` requires the target document to already
exist for those op kinds.
"""
from __future__ import annotations

from datetime import date

from schema import (
    ClassificationResult,
    DocStatus,
    ExtractionResult,
    GraphOperation,
    GraphUpdatePlan,
    GraphUpdateRationale,
    ImpactAssessment,
    LifecycleCase,
    ReinvocationRequest,
    StoredDocument,
    TermDefinition,
    TermUsage,
    ValidationReport,
)

from .base import BaseAgent

SYSTEM_PROMPT = (
    "You are the Graph-Update agent in a regulatory-document ingestion "
    "pipeline. The deterministic metadata operations for this document have "
    "already been computed by a rules engine; your job is to write a short, "
    "human-readable rationale for them, confirm/list the redefined terms (if "
    "any), and flag any warnings a human reviewer should know about. Do not "
    "invent operations; only explain the ones given to you. "
    "Respond with ONLY a JSON object matching the given JSON Schema."
)


def _effective_date(extraction: ExtractionResult) -> str:
    if extraction.effective_date:
        return extraction.effective_date
    if extraction.metadata.lifecycle_metadata.valid_from:
        return extraction.metadata.lifecycle_metadata.valid_from
    return date.today().isoformat()


def build_case_operations(
    case: LifecycleCase,
    extraction: ExtractionResult,
    report: ValidationReport,
    new_doc_id: str,
    raw_text: str,
) -> list[GraphOperation]:
    """PURE, deterministic. Implements plan section 3 exactly for all 9 cases.

    `T` = report.resolved_refs.values() (existing targets only); `d` =
    extraction.effective_date or N.valid_from or today.
    """
    targets = list(dict.fromkeys(report.resolved_refs.values()))
    d = _effective_date(extraction)

    metadata = extraction.metadata.model_copy(deep=True)
    metadata.identity_metadata.doc_id = new_doc_id
    metadata.lifecycle_metadata.status = DocStatus.ACTIVE

    if case == LifecycleCase.NEW_STATEMENT:
        pass  # create only

    elif case == LifecycleCase.FULL_REPLACEMENT:
        metadata.lineage_metadata.supersedes = list(targets)

    elif case == LifecycleCase.REPLACEMENT_WITH_CONTRADICTION:
        metadata.lineage_metadata.supersedes = list(targets)
        metadata.lineage_metadata.contradicts = list(targets)
        metadata.lifecycle_metadata.notes = list(metadata.lifecycle_metadata.notes) + list(
            extraction.contradiction_notes
        )
        if "CONTRADICTION" not in metadata.lifecycle_metadata.review_flags:
            metadata.lifecycle_metadata.review_flags.append("CONTRADICTION")

    elif case == LifecycleCase.REVOCATION_OR_EXPIRATION:
        metadata.lineage_metadata.revokes = list(targets)

    elif case == LifecycleCase.CONSOLIDATION:
        metadata.lineage_metadata.consolidates = list(targets)

    elif case == LifecycleCase.SPLITTING:
        metadata.lineage_metadata.split_from = list(targets)

    elif case == LifecycleCase.PATCH_ERRATUM:
        metadata.lineage_metadata.amends = list(targets)
        metadata.identity_metadata.doc_type = "fe_de_erratas"

    elif case == LifecycleCase.TEMPORARY_EXCEPTION:
        metadata.lineage_metadata.overrides = list(targets)
        if not metadata.lifecycle_metadata.valid_until:
            if "MISSING_EXPIRY" not in metadata.lifecycle_metadata.review_flags:
                metadata.lifecycle_metadata.review_flags.append("MISSING_EXPIRY")

    elif case == LifecycleCase.INDIRECT_DEPENDENCY_UPDATE:
        for term_def in extraction.redefined_terms:
            term = term_def.term
            if term not in metadata.identity_metadata.defined_terms:
                metadata.identity_metadata.defined_terms.append(term)
            metadata.lineage_metadata.definition_sources[term] = new_doc_id

    # Universal rule: non-empty missing_refs -> N gets missing_dependencies
    # and the MISSING_DEPENDENCY review flag, for every case.
    if report.missing_refs:
        metadata.lifecycle_metadata.missing_dependencies = list(report.missing_refs)
        if "MISSING_DEPENDENCY" not in metadata.lifecycle_metadata.review_flags:
            metadata.lifecycle_metadata.review_flags.append("MISSING_DEPENDENCY")

    stored = StoredDocument(metadata=metadata, raw_text=raw_text)
    ops: list[GraphOperation] = [
        GraphOperation(
            op="create_document",
            doc_id=new_doc_id,
            value=stored.model_dump(mode="json"),
            reason=f"create {new_doc_id} ({case.value})",
        )
    ]

    # ---- ops on each existing target t in T ----
    if case == LifecycleCase.FULL_REPLACEMENT:
        for t in targets:
            ops.append(
                GraphOperation(
                    op="set_status",
                    doc_id=t,
                    value={"status": DocStatus.SUPERSEDED.value, "valid_until": d},
                    reason=f"superseded by {new_doc_id}",
                )
            )
            ops.append(GraphOperation(op="append_lineage", doc_id=t, field="superseded_by", value=new_doc_id))

    elif case == LifecycleCase.REPLACEMENT_WITH_CONTRADICTION:
        total = extraction.contradiction_scope == "total"
        for t in targets:
            if total:
                ops.append(
                    GraphOperation(
                        op="set_status",
                        doc_id=t,
                        value={"status": DocStatus.SUPERSEDED.value, "valid_until": d},
                        reason="total contradiction",
                    )
                )
            else:
                ops.append(
                    GraphOperation(
                        op="set_status",
                        doc_id=t,
                        value={"status": DocStatus.PARTIALLY_SUPERSEDED.value},
                        reason="partial contradiction",
                    )
                )
            ops.append(GraphOperation(op="append_lineage", doc_id=t, field="superseded_by", value=new_doc_id))
            ops.append(
                GraphOperation(op="add_review_flag", doc_id=t, value=f"CONTRADICTED_BY:{new_doc_id}")
            )

    elif case == LifecycleCase.REVOCATION_OR_EXPIRATION:
        status = DocStatus.EXPIRED if extraction.revocation_kind == "expiration" else DocStatus.REVOKED
        for t in targets:
            ops.append(
                GraphOperation(
                    op="set_status",
                    doc_id=t,
                    value={"status": status.value, "valid_until": d},
                    reason=extraction.revocation_kind or "revocation",
                )
            )
            ops.append(GraphOperation(op="append_lineage", doc_id=t, field="revoked_by", value=new_doc_id))

    elif case == LifecycleCase.CONSOLIDATION:
        for t in targets:
            ops.append(
                GraphOperation(
                    op="set_status",
                    doc_id=t,
                    value={"status": DocStatus.SUPERSEDED.value, "valid_until": d},
                    reason=f"consolidated into {new_doc_id}",
                )
            )
            ops.append(GraphOperation(op="append_lineage", doc_id=t, field="superseded_by", value=new_doc_id))

    elif case == LifecycleCase.SPLITTING:
        for t in targets:
            ops.append(
                GraphOperation(
                    op="set_status",
                    doc_id=t,
                    value={"status": DocStatus.SUPERSEDED.value, "valid_until": d},
                    reason=f"split into {new_doc_id}",
                )
            )
            ops.append(GraphOperation(op="append_lineage", doc_id=t, field="split_into", value=new_doc_id))
            ops.append(GraphOperation(op="append_lineage", doc_id=t, field="superseded_by", value=new_doc_id))

    elif case == LifecycleCase.PATCH_ERRATUM:
        for t in targets:
            for patch in extraction.patches:
                patch_value = patch.model_copy(update={"patched_by": new_doc_id, "effective_date": d})
                ops.append(
                    GraphOperation(
                        op="append_patch",
                        doc_id=t,
                        value=patch_value.model_dump(mode="json"),
                        reason="erratum",
                    )
                )

    elif case == LifecycleCase.TEMPORARY_EXCEPTION:
        valid_from = metadata.lifecycle_metadata.valid_from or ""
        valid_until = metadata.lifecycle_metadata.valid_until or ""
        for t in targets:
            ops.append(GraphOperation(op="append_lineage", doc_id=t, field="overridden_by", value=new_doc_id))
            ops.append(
                GraphOperation(
                    op="add_review_flag",
                    doc_id=t,
                    value=f"TEMP_EXCEPTION:{new_doc_id}:{valid_from}..{valid_until}",
                )
            )

    # INDIRECT_DEPENDENCY_UPDATE has no ops on T here: the per-affected-doc
    # effects happen later, via loop 2 / build_impact_operations.

    return ops


def build_impact_operations(
    request: ReinvocationRequest,
    assessment: ImpactAssessment,
    usage: TermUsage | None,
) -> list[GraphOperation]:
    """Case-9 per-affected-doc ops, only when `assessment.affected` is true.

    Note: `notes += usage clauses` from the plan's table cannot be a true
    append in a pure, storage-less function (there is nothing to read the
    prior notes from), so it is expressed as a `set_lifecycle_field` that
    sets `notes` to this usage's clauses. This is a deliberate, documented
    deviation from a strict "+=" reading, forced by the fixed, storage-less
    signature.
    """
    if not assessment.affected:
        return []

    target = request.target_doc_id
    source = request.source_doc_id
    term = request.term

    ops: list[GraphOperation] = [
        GraphOperation(
            op="set_definition_source",
            doc_id=target,
            field=term,
            value=source,
            reason=f"term '{term}' redefined by {source}",
        ),
        GraphOperation(
            op="add_review_flag",
            doc_id=target,
            value=f"TERM_REDEFINED:{term}:{source}",
            reason="indirect dependency update",
        ),
    ]
    if usage is not None and usage.clauses:
        ops.append(
            GraphOperation(
                op="set_lifecycle_field",
                doc_id=target,
                field="notes",
                value=list(usage.clauses),
                reason=f"usage of redefined term '{term}'",
            )
        )
    ops.append(
        GraphOperation(
            op="append_lineage",
            doc_id=source,
            field="impacts",
            value=target,
            reason=f"{target} affected by redefinition of '{term}'",
        )
    )
    return ops


class GraphUpdateAgent(BaseAgent):
    name = "graph_update"

    def plan(
        self,
        classification: ClassificationResult,
        extraction: ExtractionResult,
        report: ValidationReport,
        new_doc_id: str,
        raw_text: str,
    ) -> GraphUpdatePlan:
        operations = build_case_operations(classification.case, extraction, report, new_doc_id, raw_text)
        user_prompt = (
            f"case: {classification.case.value}\n"
            f"new_doc_id: {new_doc_id}\n"
            f"operation_count: {len(operations)}\n"
            f"redefined_terms: {[t.model_dump() for t in extraction.redefined_terms]}\n"
        )
        rationale = self._llm_json(
            task="graph_update",
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_model=GraphUpdateRationale,
            context={
                "case": classification.case.value,
                "operations": [op.model_dump(mode="json") for op in operations],
                "redefined_terms": [t.model_dump(mode="json") for t in extraction.redefined_terms],
            },
            doc_id=new_doc_id,
            attempt=classification.attempt,
        )
        return GraphUpdatePlan(
            case=classification.case,
            new_doc_id=new_doc_id,
            operations=operations,
            rationale=rationale.rationale,
            impact_terms=rationale.impact_terms or list(extraction.redefined_terms),
            warnings=rationale.warnings,
        )

    def apply(self, plan: GraphUpdatePlan) -> int:
        applied = 0
        for op in plan.operations:
            try:
                self.storage.apply_operation(op)
            except KeyError as exc:
                self.logger.log(
                    "error",
                    agent=self.name,
                    message=f"failed to apply {op.op} on {op.doc_id}: {exc}",
                    input=op,
                    doc_id=plan.new_doc_id,
                )
                continue
            self.logger.log(
                "storage_op",
                agent=self.name,
                message=f"applied {op.op} on {op.doc_id}",
                input=op,
                doc_id=plan.new_doc_id,
            )
            applied += 1
        return applied

    def find_impact_targets(
        self,
        new_doc_id: str,
        terms: list[TermDefinition],
        exclude: set[str],
    ) -> list[ReinvocationRequest]:
        seen: set[str] = set()
        requests: list[ReinvocationRequest] = []
        for term_def in terms:
            targets = self.storage.find_active_documents_referencing_term(
                term_def.term, exclude=exclude | {new_doc_id}
            )
            for target_doc_id in targets:
                if target_doc_id in seen:
                    continue
                seen.add(target_doc_id)
                requests.append(
                    ReinvocationRequest(
                        source_doc_id=new_doc_id,
                        target_doc_id=target_doc_id,
                        term=term_def.term,
                        new_definition=term_def.definition,
                    )
                )
                if len(requests) >= self.settings.max_impact_docs:
                    return requests
        return requests

    def apply_impact(
        self,
        request: ReinvocationRequest,
        assessment: ImpactAssessment,
        usage: TermUsage | None,
    ) -> int:
        ops = build_impact_operations(request, assessment, usage)
        applied = 0
        for op in ops:
            try:
                self.storage.apply_operation(op)
            except KeyError as exc:
                self.logger.log(
                    "error",
                    agent=self.name,
                    message=f"failed to apply {op.op} on {op.doc_id}: {exc}",
                    input=op,
                    doc_id=request.target_doc_id,
                )
                continue
            self.logger.log(
                "storage_op",
                agent=self.name,
                message=f"applied {op.op} on {op.doc_id}",
                input=op,
                doc_id=request.target_doc_id,
            )
            applied += 1
        return applied
