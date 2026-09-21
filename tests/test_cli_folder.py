"""The launcher's 'is this an entries folder' test: entries one level down count, a stray Word file does not."""
import os, tempfile, unittest
from pxrd_review import cli


class HasEntryDocx(unittest.TestCase):
    def _tree(self, *files):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        for f in files:
            p = os.path.join(t.name, f)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, 'w').close()
        return t.name

    def test_entries_one_level_down(self):
        self.assertTrue(cli._has_entry_docx(self._tree('Part 2/I003448(Testite).docx')))
        self.assertTrue(cli._has_entry_docx(self._tree('Part 2/O12345(Testite)_edited.docx')))

    def test_a_stray_word_file_one_level_down_is_not_an_entry(self):
        self.assertFalse(cli._has_entry_docx(self._tree('grants/ICDD commitment statement.docx',
                                                        'notes/Outline.docx')))

    def test_the_tools_own_output_does_not_count(self):
        self.assertFalse(cli._has_entry_docx(self._tree('review_out/I003448(Testite).docx',
                                                        'review_out_ours/I003448(Testite)_edited.docx')))


if __name__ == '__main__':
    unittest.main()
