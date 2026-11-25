import unittest
from titan.pending_triage import triage


class PendingTests(unittest.TestCase):
    def test_cutoff_and_partition(self):
        rows = [dict(event_id=str(i), unanswered_question="How large?", why_it_matters="Sales",
                     next_checkpoint="Morning") for i in range(105)]
        meta = {"99": {"event_type": "results"}, "100": {"event_type": "award",
                "size_vs_annual_sales": 0.4}, "101": {"event_type": "guidance",
                "public_time": "2026-11-26T10:00:00Z"}}
        def run(items):
            return triage(items, meta, "2026-11-25T08:30:00+05:30")
        result = run(rows)
        self.assertEqual(result, run(reversed(rows)))
        self.assertEqual([result[k] for k in ("pending_total","deep_assess_count","carry_pending_count")],
                         [105,12,93])
        self.assertEqual([r["event_id"] for r in result["deep_assess"][:2]], ["100","99"])
        self.assertEqual(result["carry_pending"][-1]["event_id"], "101")
        self.assertEqual({r["event_id"] for r in result["deep_assess"]+result["carry_pending"]},
                         {r["event_id"] for r in rows})

    def test_incomplete_carry_fields_fail_explicitly(self):
        with self.assertRaisesRegex(ValueError,"Incomplete pending"):
            triage([{"event_id":"event"}], {}, "2026-11-25T08:30:00Z")
