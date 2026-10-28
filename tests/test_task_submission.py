"""Verify that scientific input and pilot failures prevent bulk submission."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from imaging.config import load_config, module_path
from imaging.rest import write_csv


REPO = Path(__file__).resolve().parents[1]
SOURCE = (REPO / "scripts/neuroimaging/submit_task_background.sbatch").read_text(encoding="utf-8")
PYTHON = SOURCE.split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]


class SubmissionGates(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="efny_submission_")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.registry = self.root / "run.json"
        self.configs = {task: load_config(REPO / "configs/neuroimaging_stc.json", "THU", self.root, "task", task)
                        for task in ("sst", "nback", "switch")}

    def execute(self, phase):
        with patch("sys.argv", ["-", phase, str(self.registry), "all"]), \
             patch.dict(os.environ, {"SLURM_JOB_ID": "100"}), \
             patch("imaging.config.load_config", side_effect=lambda *args, **kwargs: self.configs[kwargs["task"]]), \
             patch("subprocess.check_output", side_effect=lambda command, **kwargs:
                   "testcommit\n" if command[:2] == ["git", "rev-parse"] else ""), \
             patch("imaging.pipeline.submit") as submit:
            with self.assertRaises(AssertionError):
                exec(compile(PYTHON, "submit_task_background.sbatch", "exec"), {})
            submit.assert_not_called()

    def test_available_but_invalid_design_blocks_all_tasks(self):
        for task, config in self.configs.items():
            logs = module_path(config, "xcpd", "logs")
            logs.mkdir(parents=True)
            row = dict(scan_id="sub-test_task-" + task, subject="sub-test", ready=True,
                       frame_offset_seconds=0.96, columns=["task_cue"], issues=[])
            if task == "switch":
                row.update(ready=False, issues=["task frame offset differs from STC BOLD StartTime"])
            (logs / "confounds_audit.json").write_text(json.dumps([row]), encoding="utf-8")
            (logs / "subjects_ready.txt").write_text("sub-test\n" if row["ready"] else "", encoding="utf-8")
        self.execute("pilot")
        self.assertFalse(self.registry.exists())

    def test_failed_pilot_audit_blocks_batch_for_every_task(self):
        self.registry.write_text(json.dumps(dict(code_commit="testcommit", tasks={
            task: dict(subjects=["sub-test", "sub-next"], pilots=["sub-test"])
            for task in self.configs})), encoding="utf-8")

        def check(config, stage, scans):
            write_csv(module_path(config, "xcpd", "logs") / "completion_audit.csv", [
                dict(subject="sub-test", complete="false" if config["task"] == "nback" else "true")])

        with patch("imaging.pipeline.background_scans", return_value=[dict(subject="sub-test")]), \
             patch("imaging.pipeline.check", side_effect=check):
            self.execute("batch")


if __name__ == "__main__":
    unittest.main()
