from __future__ import annotations
import re
from typing import Any
from .models import Criterion, RankedSupplier, ValidatedSupplier

def validate_active_criteria(criteria: list[Criterion]) -> None:
    active = [c for c in criteria if c.is_active]
    if not active: raise ValueError("At least one active criterion is required.")
    total = sum(c.weight for c in active)
    if abs(total - 100) > 0.001: raise ValueError(f"Active criteria weights must total 100; got {total}.")

def _comparable_text(value: str) -> str: return re.sub(r"\s+", " ", value).strip().casefold()

def normalize_scorecard(raw: Any, supplier_name: str, criteria: list[Criterion], document_text: str | None = None) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    if not isinstance(raw, dict): warnings.append("LLM output was not a JSON object; all criteria were normalized to zero."); raw = {}
    elif not isinstance(raw.get("criteria", []), list): warnings.append("LLM output field 'criteria' was not a list; all criteria were normalized to zero."); raw = {**raw, "criteria": []}
    active = {c.criterion_id: c for c in criteria if c.is_active}; by_id: dict[int, dict[str, Any]] = {}
    for item in raw.get("criteria", []):
        if not isinstance(item, dict): warnings.append("Ignored a non-object criterion result."); continue
        try: criterion_id = int(item.get("criterion_id"))
        except (TypeError, ValueError): warnings.append("Ignored a criterion result without a valid criterion_id."); continue
        if criterion_id not in active: warnings.append(f"Ignored unknown or inactive criterion_id {criterion_id}."); continue
        if criterion_id in by_id: warnings.append(f"Duplicate criterion_id {criterion_id}; kept the first result."); continue
        by_id[criterion_id] = item
    normalized: list[dict[str, Any]] = []
    for criterion_id, criterion in active.items():
        item = by_id.get(criterion_id)
        if item is None:
            warnings.append(f"Missing {criterion.name}; assigned a score of 0.")
            normalized.append({"criterion_id": criterion_id, "score": 0, "max_score": criterion.max_score, "justification": "No valid LLM result was supplied.", "evidence": "", "evidence_page": None, "evidence_verified": False, "confidence": 0.0}); continue
        try: score = float(item.get("score"))
        except (TypeError, ValueError): score = 0; warnings.append(f"Invalid score for {criterion.name}; assigned 0.")
        clipped = min(max(score, 0), criterion.max_score)
        if clipped != score: warnings.append(f"Clipped {criterion.name} score from {score} to {clipped}.")
        evidence = str(item.get("evidence") or "").strip(); justification = str(item.get("justification") or "").strip()
        try: evidence_page = int(item["evidence_page"]) if item.get("evidence_page") is not None else None
        except (TypeError, ValueError): evidence_page = None; warnings.append(f"Invalid evidence page for {criterion.name}.")
        evidence_verified = bool(evidence)
        if evidence and document_text is not None:
            evidence_verified = _comparable_text(evidence) in _comparable_text(document_text)
            if not evidence_verified: warnings.append(f"{criterion.name} evidence could not be verified against the extracted proposal text.")
        if not evidence: warnings.append(f"{criterion.name} has no supporting evidence.")
        if not justification: warnings.append(f"{criterion.name} has no score justification.")
        try: model_confidence = float(item.get("confidence", 0.0))
        except (TypeError, ValueError): model_confidence = 0.0; warnings.append(f"Invalid confidence for {criterion.name}; assigned 0.")
        confidence = 0.0 if not evidence else min(max(model_confidence, 0.0), 1.0) * (0.5 if not evidence_verified else 1.0)
        normalized.append({"criterion_id": criterion_id, "score": clipped, "max_score": criterion.max_score, "justification": justification, "evidence": evidence, "evidence_page": evidence_page, "evidence_verified": evidence_verified, "confidence": confidence})
    return {"supplier_name": supplier_name, "criteria": normalized, "risks": [str(x) for x in raw.get("risks", [])] if isinstance(raw.get("risks", []), list) else [], "overall_summary": str(raw.get("overall_summary") or "")}, warnings

def rank_suppliers(suppliers: list[ValidatedSupplier], criteria: list[Criterion]) -> list[RankedSupplier]:
    validate_active_criteria(criteria); active = [c for c in criteria if c.is_active]
    scores = {s.supplier.supplier_name: {i.criterion_id: i.score for i in s.scorecard.criteria} for s in suppliers}
    benchmarks = {c.criterion_id: max((scores[s.supplier.supplier_name].get(c.criterion_id, 0) for s in suppliers), default=0) for c in active}
    results: list[RankedSupplier] = []
    for supplier in suppliers:
        criterion_rows: list[dict[str, Any]] = []; absolute_score = 0.0; ppi = 0.0; lookup = {i.criterion_id: i for i in supplier.scorecard.criteria}; evidence_coverage = 0.0; confidence_total = 0.0
        for criterion in active:
            item = lookup[criterion.criterion_id]; benchmark = benchmarks[criterion.criterion_id]; relative = 100.0 if benchmark == 0 else (item.score / benchmark) * 100
            absolute_score += (item.score / criterion.max_score) * criterion.weight; ppi += relative * (criterion.weight / 100); evidence_coverage += (1.0 if item.evidence_verified else 0.0) * (criterion.weight / 100); confidence_total += item.confidence * (criterion.weight / 100)
            criterion_rows.append({"criterion_id": criterion.criterion_id, "name": criterion.name, "weight": criterion.weight, "score": item.score, "max_score": criterion.max_score, "benchmark": benchmark, "gap": item.score - benchmark, "relative_percent": relative, "justification": item.justification, "evidence": item.evidence, "evidence_page": item.evidence_page, "evidence_verified": item.evidence_verified, "confidence": item.confidence})
        review_reasons: list[str] = []
        if evidence_coverage < 0.8: review_reasons.append(f"Only {evidence_coverage:.0%} of weighted criteria have verified proposal evidence.")
        if confidence_total < 0.7: review_reasons.append(f"Weighted evidence confidence is {confidence_total:.0%}, below the 70% review threshold.")
        if supplier.warnings: review_reasons.append(f"Validation produced {len(supplier.warnings)} warning(s).")
        results.append(RankedSupplier(supplier_name=supplier.supplier.supplier_name, submission_date=supplier.supplier.submission_date, experience_rating=supplier.supplier.experience_rating, absolute_score=round(absolute_score, 4), ppi=round(ppi, 4), final_rank=0, criteria=criterion_rows, risks=supplier.scorecard.risks, overall_summary=supplier.scorecard.overall_summary, warnings=supplier.warnings, evidence_coverage=round(evidence_coverage, 4), confidence=round(confidence_total, 4), review_required=bool(review_reasons), review_reasons=review_reasons, tie_break_explanation=""))
    results.sort(key=lambda r: (-r.ppi, r.submission_date, -r.experience_rating, r.supplier_name.casefold())); ranked: list[RankedSupplier] = []
    for index, result in enumerate(results, start=1):
        if index == 1:
            nxt = results[1] if len(results) > 1 else None
            if nxt is None or result.ppi != nxt.ppi: explanation = f"Ranked #1 because it has the highest PPI ({result.ppi:.2f})."
            elif result.submission_date != nxt.submission_date: explanation = f"Ranked #1: PPI is tied at {result.ppi:.2f}; it was submitted earlier than {nxt.supplier_name}."
            elif result.experience_rating != nxt.experience_rating: explanation = "Ranked #1: PPI and submission date are tied; it has the higher experience rating."
            else: explanation = "Ranked #1: all preceding business measures are tied; its name sorts first alphabetically."
        else:
            prior = results[index - 2]
            if result.ppi != prior.ppi: explanation = f"Ranked below {prior.supplier_name} because its PPI ({result.ppi:.2f}) is lower than {prior.ppi:.2f}."
            elif result.submission_date != prior.submission_date: explanation = f"PPI is tied with {prior.supplier_name}; ranked below because its submission date is later."
            elif result.experience_rating != prior.experience_rating: explanation = f"PPI and submission date are tied with {prior.supplier_name}; ranked below because its experience rating is lower."
            else: explanation = f"PPI, submission date, and experience rating are tied with {prior.supplier_name}; ranked below by supplier name ascending."
        ranked.append(result.model_copy(update={"final_rank": index, "tie_break_explanation": explanation}))
    return ranked

def rank_sensitivity(results: list[RankedSupplier], criteria: list[Criterion], shift_points: float = 10.0) -> dict[str, Any]:
    if len(results) < 2: return {"stable": True, "scenarios": []}
    baseline = results[0].supplier_name; scenarios: list[dict[str, Any]] = []
    for focus in (c for c in criteria if c.is_active and c.weight < 100):
        increased_weight = min(100.0, focus.weight + shift_points); remaining_total = 100.0 - focus.weight; redistributed_total = 100.0 - increased_weight
        adjusted_weights = {c.criterion_id: increased_weight if c.criterion_id == focus.criterion_id else c.weight * redistributed_total / remaining_total for c in criteria if c.is_active}
        adjusted = sorted(results, key=lambda result: (-sum(item["relative_percent"] * adjusted_weights[item["criterion_id"]] / 100 for item in result.criteria), result.submission_date, -result.experience_rating, result.supplier_name.casefold()))
        scenarios.append({"criterion": focus.name, "leader": adjusted[0].supplier_name, "leader_changed": adjusted[0].supplier_name != baseline})
    return {"stable": not any(item["leader_changed"] for item in scenarios), "scenarios": scenarios}

def detect_result_anomalies(results: list[RankedSupplier]) -> list[str]:
    anomalies: list[str] = []; signatures: dict[tuple[float, ...], list[str]] = {}
    for result in results: signatures.setdefault(tuple(item["score"] for item in result.criteria), []).append(result.supplier_name)
    for suppliers in signatures.values():
        if len(suppliers) > 1: anomalies.append("Identical criterion score vectors: " + ", ".join(suppliers) + ".")
    if results and all(all(item["benchmark"] == 0 for item in result.criteria) for result in results): anomalies.append("All supplier benchmarks are zero; ranking relies only on tie-break rules.")
    return anomalies
