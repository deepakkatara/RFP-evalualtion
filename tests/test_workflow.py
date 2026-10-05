import unittest
from app.workflow import PHASES, WORKFLOW, initial_trace, trace_lookup, update_trace_step

class WorkflowTests(unittest.TestCase):
    def test_guided_phases_are_in_user_journey_order(self):
        self.assertEqual(PHASES, ("Configuration & Evaluation Metrics", "Supplier Proposals", "Execution Flow", "Results"))
    def test_initial_trace_marks_every_stage_pending(self):
        trace = initial_trace(); self.assertEqual([s["key"] for s in trace["steps"]], [s["key"] for s in WORKFLOW]); self.assertTrue(all(s["status"] == "pending" for s in trace["steps"]))
    def test_trace_update_changes_only_the_selected_stage(self):
        trace = initial_trace(); updated = update_trace_step(trace, "ingest", "completed", "Text extracted", ["Apex: 200 characters"])
        self.assertEqual(trace_lookup(trace)["ingest"]["status"], "pending"); self.assertEqual(trace_lookup(updated)["ingest"]["status"], "completed"); self.assertEqual(trace_lookup(updated)["assess"]["status"], "pending")

if __name__ == "__main__": unittest.main()
