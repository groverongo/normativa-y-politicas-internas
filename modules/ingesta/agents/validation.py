"""ValidationAgent: deterministic reference-resolution and structural checks,
plus an LLM judgement that supplies human-readable reasoning and a feedback
hypothesis for the classifier. The deterministic logic is the reliable
trigger for loop 1 (validation_to_classifier); the LLM never overrides it.
"""
from __future__ import annotations

from schema import (
    CASES_REQUIRING_TARGETS,
    ClassificationResult,
    ExtractionResult,
    FeedbackMessage,
    LifecycleCase,
    ValidationJudgement,
    ValidationReport,
)

from .base import BaseAgent

SYSTEM_PROMPT = (
    "You are the Validation agent in a regulatory-document ingestion "
    "pipeline. You are given the classified lifecycle case, which cited "
    "references resolved against the corpus and which did not, and any "
    "structural issues already detected deterministically. Explain, in plain "
    "language, whether the pipeline should proceed, reclassify, or proceed "
    "with a missing-dependency flag, and suggest a hypothesis the classifier "
    "could use to reconsider the case if something looks wrong. "
    "Respond with ONLY a JSON object matching the given JSON Schema."
)

# All list-valued fields on LineageMetadata (excludes the dict-valued
# `definition_sources`), per plan section 2.9.
_LINEAGE_LIST_FIELDS = (
    "supersedes",
    "superseded_by",
    "amends",
    "patched_by",
    "consolidates",
    "split_from",
    "split_into",
    "contradicts",
    "revokes",
    "revoked_by",
    "overrides",
    "overridden_by",
    "impacts",
)


class ValidationAgent(BaseAgent):
    name = "validation"

    def validate(
        self,
        classification: ClassificationResult,
        extraction: ExtractionResult,
        attempt: int = 0,
    ) -> ValidationReport:
        case = classification.case
        lineage = extraction.metadata.lineage_metadata

        refs: list[str] = []
        for ref in (
            list(extraction.target_doc_ids)
            + [v for field in _LINEAGE_LIST_FIELDS for v in getattr(lineage, field)]
            + list(classification.candidate_references)
        ):
            if ref and ref not in refs:
                refs.append(ref)

        resolved_refs: dict[str, str] = {}
        missing_refs: list[str] = []
        for ref in refs:
            resolved = self.storage.resolve_doc_id(ref)
            if resolved and self.storage.check_document_exists(resolved):
                resolved_refs[ref] = resolved
            else:
                missing_refs.append(ref)

        structural_issues: list[str] = []
        if case in CASES_REQUIRING_TARGETS and not resolved_refs and not missing_refs:
            structural_issues.append("case requires target documents")
        if case == LifecycleCase.CONSOLIDATION and len(refs) < 2:
            structural_issues.append("consolidation needs >= 2 sources")
        if case == LifecycleCase.TEMPORARY_EXCEPTION and not extraction.metadata.lifecycle_metadata.valid_until:
            structural_issues.append("temporary exception without valid_until")
        if case == LifecycleCase.PATCH_ERRATUM and not extraction.patches:
            structural_issues.append("erratum without patch details")
        if case == LifecycleCase.INDIRECT_DEPENDENCY_UPDATE and not extraction.redefined_terms:
            structural_issues.append("no redefined terms")

        ok = not missing_refs and not structural_issues
        # NEW_STATEMENT-with-missing-refs exception: the document stands on
        # its own; missing refs only become a flag on the new doc, not a
        # reason to reclassify.
        new_statement_missing_only = (
            case == LifecycleCase.NEW_STATEMENT and bool(missing_refs) and not structural_issues
        )
        if new_statement_missing_only:
            ok = True

        judgement = self._llm_json(
            task="validate",
            system_prompt=SYSTEM_PROMPT,
            user_prompt=(
                f"case: {case.value}\n"
                f"resolved_refs: {resolved_refs}\n"
                f"missing_refs: {missing_refs}\n"
                f"structural_issues: {structural_issues}\n"
                f"deterministic ok: {ok}\n"
            ),
            output_model=ValidationJudgement,
            context={
                "case": case.value,
                "missing_refs": missing_refs,
                "structural_issues": structural_issues,
            },
            attempt=attempt,
        )

        if new_statement_missing_only:
            recommendation = "proceed_with_missing_dependency"
        elif not ok:
            # Deterministic trigger: never let the LLM talk its way past a
            # failed structural/reference check.
            recommendation = "reclassify"
        else:
            recommendation = judgement.recommendation

        return ValidationReport(
            ok=ok,
            resolved_refs=resolved_refs,
            missing_refs=missing_refs,
            structural_issues=structural_issues,
            recommendation=recommendation,
            reasoning=judgement.reasoning,
            feedback_hint=judgement.feedback_hint,
            attempt=attempt,
        )

    def build_feedback(
        self,
        report: ValidationReport,
        classification: ClassificationResult,
        iteration: int,
    ) -> FeedbackMessage:
        kind = "missing_dependency" if report.missing_refs else "structural_issue"
        if report.feedback_hint:
            content = report.feedback_hint
        elif kind == "missing_dependency":
            content = (
                f"Prior classification {classification.case.value} cites "
                f"references that do not resolve in the corpus: "
                f"{report.missing_refs}. Reconsider whether this document "
                f"really depends on those references."
            )
        else:
            content = (
                f"Prior classification {classification.case.value} failed "
                f"structural checks: {report.structural_issues}. Reconsider "
                f"the case."
            )
        return FeedbackMessage(
            from_agent="validation",
            to_agent="classifier",
            loop="validation_to_classifier",
            iteration=iteration,
            kind=kind,
            content=content,
            payload={
                "prior_case": classification.case.value,
                "missing_refs": report.missing_refs,
                "structural_issues": report.structural_issues,
                "resolved_refs": report.resolved_refs,
            },
        )
