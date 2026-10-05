from datetime import date
import unittest
from app.models import Criterion, LLMScorecard, SupplierInput, ValidatedSupplier
from app.evaluator import provider_defaults
from app.scoring import detect_result_anomalies, normalize_scorecard, rank_sensitivity, rank_suppliers, validate_active_criteria

CRITERIA = [Criterion(criterion_id=1, name="Technical", description="x", weight=60, max_score=10), Criterion(criterion_id=2, name="Commercial", description="x", weight=40, max_score=10)]

def supplier(name, submitted, experience, values):
    input_ = SupplierInput(supplier_name=name, submission_date=submitted, experience_rating=experience, document_text="proposal")
    card = LLMScorecard(supplier_name=name, criteria=[{"criterion_id": k, "score": v, "max_score": 10, "justification": "because", "evidence": "text"} for k, v in values.items()])
    return ValidatedSupplier(supplier=input_, scorecard=card)

class ScoringTests(unittest.TestCase):
    def test_normalization_fills_clips_and_ignores_unknowns(self):
        result, warnings = normalize_scorecard({"criteria": [{"criterion_id": 1, "score": 14}, {"criterion_id": 99, "score": 9}]}, "A", CRITERIA)
        self.assertEqual(result["criteria"][0]["score"], 10); self.assertEqual(result["criteria"][1]["score"], 0); self.assertTrue(any("unknown" in w for w in warnings)); self.assertTrue(any("Missing Commercial" in w for w in warnings))
    def test_ppi_sort_precedes_absolute_score_and_then_date(self):
        early = supplier("Early", date(2026, 1, 1), 2, {1: 8, 2: 8}); late = supplier("Late", date(2026, 1, 2), 9, {1: 8, 2: 8}); ranked = rank_suppliers([late, early], CRITERIA)
        self.assertEqual([r.supplier_name for r in ranked], ["Early", "Late"]); self.assertEqual([r.final_rank for r in ranked], [1, 2])
    def test_zero_benchmark_is_safe(self):
        ranked = rank_suppliers([supplier("A", date(2026, 1, 1), 1, {1: 0, 2: 0}), supplier("B", date(2026, 1, 2), 1, {1: 0, 2: 0})], CRITERIA)
        self.assertEqual(ranked[0].ppi, 100); self.assertTrue(all(row["relative_percent"] == 100 for row in ranked[0].criteria))
    def test_weights_must_equal_100(self):
        with self.assertRaisesRegex(ValueError, "total 100"): validate_active_criteria([Criterion(criterion_id=1, name="bad", description="x", weight=99, max_score=10)])
    def test_non_object_llm_output_becomes_zero_scorecard_with_warning(self):
        result, warnings = normalize_scorecard(["not", "an", "object"], "A", CRITERIA); self.assertEqual([i["score"] for i in result["criteria"]], [0, 0]); self.assertTrue(any("not a JSON object" in w for w in warnings))
    def test_evidence_is_verified_against_the_extracted_proposal(self):
        raw = {"criteria": [{"criterion_id": 1, "score": 8, "evidence": "Supports API integration.", "evidence_page": 2, "confidence": 0.9}, {"criterion_id": 2, "score": 7, "evidence": "invented quotation", "confidence": 0.9}]}
        result, warnings = normalize_scorecard(raw, "A", CRITERIA, "[Page 2]\nSupports API integration.")
        self.assertTrue(result["criteria"][0]["evidence_verified"]); self.assertEqual(result["criteria"][0]["confidence"], 0.9); self.assertFalse(result["criteria"][1]["evidence_verified"]); self.assertEqual(result["criteria"][1]["confidence"], 0.45); self.assertTrue(any("could not be verified" in w for w in warnings))
    def test_unverified_or_low_confidence_results_require_review(self):
        ranked = rank_suppliers([supplier("Low evidence", date(2026, 1, 1), 5, {1: 8, 2: 7})], CRITERIA); self.assertTrue(ranked[0].review_required); self.assertTrue(ranked[0].review_reasons)
    def test_sensitivity_and_anomaly_checks_do_not_change_the_rank(self):
        ranked = rank_suppliers([supplier("First", date(2026, 1, 1), 5, {1: 8, 2: 8}), supplier("Second", date(2026, 1, 2), 5, {1: 8, 2: 8})], CRITERIA)
        self.assertTrue(rank_sensitivity(ranked, CRITERIA)["stable"]); self.assertTrue(any("Identical criterion score vectors" in x for x in detect_result_anomalies(ranked)))
    def test_tie_break_explanation_identifies_submission_date(self):
        ranked = rank_suppliers([supplier("Late", date(2026, 1, 2), 9, {1: 8, 2: 8}), supplier("Early", date(2026, 1, 1), 2, {1: 8, 2: 8})], CRITERIA)
        self.assertIn("submitted earlier", ranked[0].tie_break_explanation); self.assertIn("submission date is later", ranked[1].tie_break_explanation)
    def test_known_provider_defaults_are_openai_compatible(self):
        self.assertEqual(provider_defaults("OpenRouter")["base_url"], "https://openrouter.ai/api/v1"); self.assertEqual(provider_defaults("Cohere")["base_url"], "https://api.cohere.ai/compatibility/v1")
