"""The triage merge must never overturn the reviewer's current decision (issue #1).

Triage is keyed by the docx stem, and which copy `discover` picks for an entry id changes
mid-review, so records for one entry accumulate under several stems and are merged. The merge used
to take the strongest verdict across stems, which quietly restored a `confirm` the reviewer had
since changed to `dismiss` — and `annotate_review --triage` then wrote the comment they dismissed
back into the docx, on every launch. These tests pin the rule that replaced it: the current stem is
the reviewer speaking now, and another stem may only fill in a finding it never recorded.
"""
import unittest

from pxrd_review.gui import review_gui as G

CUR = 'I003511(Foo)_edited'
OLD = 'I003511(Foo)'


def reconcile(triage, order=(CUR,)):
    """Run the merge over a triage dict -> the record for the first (current) stem."""
    saved = (G.STATE.get('triage'), G.STATE.get('order'))
    try:
        G.STATE['triage'] = triage
        G.STATE['order'] = list(order)
        G._reconcile_triage_keys()
        return G.STATE['triage'][order[0]]
    finally:
        G.STATE['triage'], G.STATE['order'] = saved


class TriageMerge(unittest.TestCase):
    def test_a_stale_confirm_does_not_overturn_the_dismiss_made_now(self):
        r = reconcile({OLD: {'findings': {'f1': {'verdict': 'confirm'}}},
                       CUR: {'findings': {'f1': {'verdict': 'dismiss'}}}})
        self.assertEqual(r['findings']['f1']['verdict'], 'dismiss')

    def test_a_cleared_verdict_stays_cleared(self):
        # un-toggling is a decision too: the old stem's confirm must not resurrect it
        r = reconcile({OLD: {'findings': {'f1': {'verdict': 'confirm'}}},
                       CUR: {'findings': {'f1': {'verdict': None}}}})
        self.assertIsNone(r['findings']['f1']['verdict'])

    def test_a_verdict_the_current_stem_never_recorded_is_still_recovered(self):
        # what the merge exists for: f1 was orphaned by the stem change, f2 was decided again
        r = reconcile({OLD: {'findings': {'f1': {'verdict': 'confirm'}, 'f2': {'verdict': 'dismiss'}}},
                       CUR: {'findings': {'f2': {'verdict': 'confirm'}}}})
        self.assertEqual(r['findings']['f1']['verdict'], 'confirm')
        self.assertEqual(r['findings']['f2']['verdict'], 'confirm')

    def test_with_no_record_for_the_current_stem_the_others_still_rank(self):
        r = reconcile({OLD: {'findings': {'f1': {'verdict': 'dismiss'}}},
                       OLD + '_x': {'findings': {'f1': {'verdict': 'confirm'}}}})
        self.assertEqual(r['findings']['f1']['verdict'], 'confirm')

    def test_a_stale_look_is_dropped_and_the_other_fields_carry_over(self):
        r = reconcile({OLD: {'note': 'from the old stem', 'findings': {'f1': {'verdict': 'look', 'label': 'cell'}}},
                       CUR: {'findings': {'f1': {'verdict': 'confirm'}}}})
        self.assertEqual(r['findings']['f1']['verdict'], 'confirm')
        self.assertEqual(r['findings']['f1']['label'], 'cell')      # a label the current stem lacks is filled in
        self.assertEqual(r['note'], 'from the old stem')

    def test_the_current_stems_own_entry_fields_win(self):
        r = reconcile({OLD: {'accept': 'x', 'findings': {}},
                       CUR: {'accept': None, 'findings': {}}})
        self.assertIsNone(r['accept'])                              # the reviewer cleared it on the copy in front of them
        r = reconcile({OLD: {'reviewed': True, 'findings': {}},
                       CUR: {'findings': {}}})
        self.assertTrue(r['reviewed'])                              # 'reviewed' is monotone: it ORs across stems


if __name__ == '__main__':
    unittest.main()
