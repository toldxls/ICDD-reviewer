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


class FolderMemory(unittest.TestCase):
    """What the launcher remembers, and what `pxrd gui` does with nothing to open."""
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.addCleanup(self.t.cleanup)
        self._mem = cli.MEM; cli.MEM = os.path.join(self.t.name, 'last.json')
        self.addCleanup(lambda: setattr(cli, 'MEM', self._mem))
        self._tmp = cli._is_temp; cli._is_temp = lambda f: False                # these batches live in a temp dir
        self.addCleanup(lambda: setattr(cli, '_is_temp', self._tmp))

    def test_a_home_folder_or_a_drive_is_never_remembered(self):
        self.assertTrue(cli.is_broad_path(os.path.expanduser('~')))
        self.assertTrue(cli.is_broad_path(os.path.abspath(os.sep)))
        self.assertFalse(cli.is_broad_path(self.t.name))
        cli._save('gui', os.path.expanduser('~'))
        self.assertEqual(cli._load(), {})
        batch = os.path.join(self.t.name, 'Part 1'); os.makedirs(batch)
        cli._save('gui', batch)
        self.assertEqual(cli._load()['gui'], os.path.abspath(batch))
        self.assertEqual(cli.recent(), [os.path.abspath(batch)])
        os.rmdir(batch)
        self.assertEqual(cli.recent(), [])                                  # a recent folder that is gone is not offered
        cli._is_temp = self._tmp
        cli._save('gui', self.t.name)                                       # a temp folder (a test's own) is never remembered
        self.assertNotIn(os.path.abspath(self.t.name), cli._load().get('recent'))

    def test_gui_with_nothing_to_open_starts_on_the_chooser(self):
        cwd = os.getcwd(); os.chdir(self.t.name); self.addCleanup(lambda: os.chdir(cwd))
        self.assertEqual(cli._resolve_folder('gui', []), (None, []))         # nothing remembered: the GUI has a picker of its own
        cli._save('gui', os.path.join(self.t.name, 'gone'))
        self.assertEqual(cli._resolve_folder('gui', []), (None, []))         # the remembered folder no longer exists
        with self.assertRaises(SystemExit):
            cli._resolve_folder('review', [])                                # the other tools can only stop


if __name__ == '__main__':
    unittest.main()
