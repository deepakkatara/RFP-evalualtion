import tempfile
import unittest
from pathlib import Path
from app.database import active_criteria, create_run, export_run, fail_run, initialize, update_criteria, update_run_trace

class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.db = Path(self.tmp.name) / "test.db"; initialize(self.db)
    def tearDown(self): self.tmp.cleanup()
    def test_failed_run_is_created_before_evaluation_and_preserves_error(self):
        run_id = create_run(self.db); fail_run(self.db, run_id, "Unreadable PDF"); exported = export_run(self.db, run_id)
        self.assertEqual(exported["run"]["status"], "failed"); self.assertEqual(exported["run"]["error_message"], "Unreadable PDF"); self.assertEqual(exported["supplier_results"], [])
    def test_run_trace_is_exported_for_workflow_explainability(self):
        run_id = create_run(self.db); update_run_trace(self.db, run_id, {"steps": [{"key": "configure", "status": "completed", "summary": "Settings ready", "details": ["100%"]}]})
        self.assertEqual(export_run(self.db, run_id)["run"]["trace"]["steps"][0]["key"], "configure")
    def test_criteria_updates_require_active_weights_to_equal_100(self):
        criteria = active_criteria(self.db); criteria[0] = criteria[0].model_copy(update={"weight": 29})
        with self.assertRaisesRegex(ValueError, "total 100"): update_criteria(self.db, criteria)
