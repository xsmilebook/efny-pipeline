"""Protect rest/upstream data when enumerating an authorized task XCP-D refresh."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from imaging.config import load_config, module_path
from scripts.neuroimaging.refresh_thu_task_confounds import task_cleanup_targets


ROOT = Path(__file__).resolve().parents[1]


class TaskCleanupScope(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="efny_task_refresh_")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.configs = [load_config(ROOT / "configs/neuroimaging_stc.json", "THU", self.root, "task", task)
                        for task in ("sst", "nback", "switch")]

    def test_only_task_outputs_and_caches_are_enumerated(self):
        owners, _ = task_cleanup_targets(self.configs)
        for owner in owners:
            owner.mkdir(parents=True)
            (owner / "sub-test").mkdir()
        protected = [self.root / "data/interim/neuroimaging/xcpd/THU/rest/sub-test",
                     module_path(self.configs[0], "fmriprep", "interim") / "sub-test"]
        for path in protected:
            path.mkdir(parents=True)
            (path / "keep.txt").write_text("preserve")
        owners, targets = task_cleanup_targets(self.configs)
        self.assertEqual(len(owners), 12)
        self.assertEqual(len(targets), 12)
        self.assertTrue(all(target.name == "sub-test" for target in targets))
        self.assertFalse(set(targets) & set(protected))
        self.assertTrue(all((p / "keep.txt").read_text() == "preserve" for p in protected))

    def test_redirected_owner_or_child_is_rejected(self):
        owners, _ = task_cleanup_targets(self.configs)
        owner = owners[0]
        owner.mkdir(parents=True)
        child = owner / "sub-test"
        child.mkdir()
        original = Path.is_symlink
        for redirected in (owner, child):
            with self.subTest(path=redirected), patch.object(Path, "is_symlink",
                    lambda path: path == redirected or original(path)):
                with self.assertRaises(AssertionError):
                    task_cleanup_targets(self.configs)

    def test_rest_configuration_is_rejected(self):
        rest = load_config(ROOT / "configs/neuroimaging_stc.json", "THU", self.root)
        with self.assertRaises(AssertionError):
            task_cleanup_targets([rest])


if __name__ == "__main__":
    unittest.main()
