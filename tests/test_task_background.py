"""Scientific identity, timing and per-run FC tests; all synthetic products are removed."""

import csv
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import nibabel as nib
import numpy as np
from nibabel.cifti2 import BrainModelAxis, ParcelsAxis, SeriesAxis

from imaging.background import (
    compute_background_fc, inspect_confounds, prepare_background, regression_config,
    validate_background_fc, validate_background_inputs, validate_joint_design,
)
from imaging.config import load_config, module_path, shell_config
from imaging.pipeline import (
    assert_completed, background_scans, check, finish_container, input_scans, prepare,
    processing_settings, record_path, run_stage, start_container, submit, validate_time_axes,
)
from imaging.rest import compute_motion, derivative_path, read_csv


REPO = Path(__file__).resolve().parents[1]
BASH = os.environ.get("EFNY_TEST_BASH") if os.name == "nt" else shutil.which("bash")


class BackgroundTests(unittest.TestCase):
    def setUp(self):
        (REPO / "temp").mkdir(exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix="smoke_task_background_", dir=REPO / "temp"))
        self.config = load_config(REPO / "configs/neuroimaging_stc.json", "THU", self.root, "task", "nback")
        self.config["bids_dir"] = str(self.root / "bids")
        self.config["datasets"]["THU"]["bids_dir"] = self.config["bids_dir"]
        self.config["task_xcpd"]["confounds_dir"] = str(self.root / "custom")
        (self.root / "custom").mkdir()
        (self.root / "custom/dataset_description.json").write_text('{"DatasetType":"derivative","GeneratedBy":[{"Name":"synthetic","Version":"1"}]}', encoding="utf-8")
        self.config["atlases"] = {"synthetic": 3}
        self.subject = "sub-THU0001"
        (self.root / "configs").mkdir()
        shutil.copyfile(REPO / "configs/xcpd_36p_task_background.yml", self.root / "configs/xcpd_36p_task_background.yml")
        self.rng = np.random.default_rng(81)
        self.custom_values = {}
        self.confounds_columns = regression_config(self.config)["confounds"]["preproc_confounds"]["columns"]
        for task, run in (("nback", "1"), ("nback", "10"), ("sst", ""), ("switch", "")):
            scan_id = f"{self.subject}_task-{task}" + (f"_run-{run}" if run else "")
            scan = dict(dataset="THU", subject=self.subject, run=run, scan_id=scan_id, func_dir="func", task=task,
                        source_bold=str(self.root / "bids" / self.subject / "func" / (scan_id + "_bold.nii.gz")))
            source = Path(scan["source_bold"])
            source.parent.mkdir(parents=True, exist_ok=True)
            nib.save(nib.Nifti1Image(np.zeros((1, 1, 1, 100)), np.eye(4)), source)
            source.with_name(scan_id + "_bold.json").write_text('{"SliceTiming":[0,1.92],"RepetitionTime":2}', encoding="utf-8")
            brain = BrainModelAxis.from_mask(np.ones(3, dtype=bool), name="CortexLeft")
            dest = derivative_path(self.config, scan, "fmriprep", "space-fsLR_den-91k_bold.dtseries.nii")
            dest.parent.mkdir(parents=True, exist_ok=True)
            nib.save(nib.Cifti2Image(self.rng.normal(size=(100, 3)),
                     header=nib.Cifti2Header.from_axes((SeriesAxis(0, 2, 100), brain))), dest)
            dest = derivative_path(self.config, scan, "fmriprep", "space-MNI152NLin2009cAsym_desc-preproc_bold.nii.gz")
            shutil.copyfile(source, dest)
            dest.with_name(scan_id + "_space-MNI152NLin2009cAsym_desc-preproc_bold.json").write_text(
                '{"SliceTimingCorrected":true,"StartTime":0.96,"RepetitionTime":2}', encoding="utf-8")
            preproc = derivative_path(self.config, scan, "fmriprep", "desc-confounds_timeseries.tsv")
            with preproc.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream, delimiter="\t")
                writer.writerow([*self.confounds_columns, "framewise_displacement"])
                for i, row in enumerate(self.rng.normal(size=(100, 36))):
                    writer.writerow([*row, "n/a" if i == 0 else 0.1])
            columns = {"nback": ["task_0back", "task_2back", "task_cue"],
                       "sst": ["task_go_correct", "task_stop_success"],
                       "switch": ["task_cue", "task_nonswitch1", "task_nonswitch2", "task_switch"]}[task]
            values = self.rng.normal(size=(100, len(columns)))
            self.custom_values[scan_id] = (columns, values)
            custom = self.root / "custom" / self.subject / "func" / (scan_id + "_desc-confounds_timeseries.tsv")
            custom.parent.mkdir(parents=True, exist_ok=True)
            with custom.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream, delimiter="\t")
                writer.writerow(columns)
                writer.writerows(values)
            metadata = {c: {"Description": "SPM canonical HRF task effect to remove"} for c in columns}
            metadata["TaskDesignProvenance"] = dict(SourceBOLD=str(source), SourceCSV="synthetic.csv",
                RepetitionTime=2, NFrames=100, FrameTimeOffsetSeconds=0.96, DummyVolumesRemovedHere=0)
            custom.with_suffix(".json").write_text(json.dumps(metadata), encoding="utf-8")
        root = module_path(self.config, "fmriprep", "interim")
        (root / "dataset_description.json").write_text('{"DatasetType":"derivative"}', encoding="utf-8")
        (root / f"{self.subject}.html").write_text("synthetic report", encoding="utf-8")
        prepare(self.config, None)
        self.upstream = input_scans(self.config)
        with patch("imaging.pipeline.subprocess.check_output", return_value="synthetic"):
            finish_container(self.config, "fmriprep", self.subject, self.upstream, ["mock"], "mock-fmriprep")
        prepare_background(self.config, self.upstream, None)
        self.scans = background_scans(self.config)

    def tearDown(self):
        assert self.root.resolve().is_relative_to((REPO / "temp").resolve())
        shutil.rmtree(self.root)

    def custom_file(self, scan):
        return Path(self.config["task_xcpd"]["confounds_dir"]) / self.subject / "func" / (
            scan["scan_id"] + "_desc-confounds_timeseries.tsv")

    def write_outputs(self):
        root = module_path(self.config, "xcpd", "interim")
        root.mkdir(parents=True)
        (root / "dataset_description.json").write_text('{"DatasetType":"derivative"}', encoding="utf-8")
        (root / f"{self.subject}.html").write_text("synthetic report", encoding="utf-8")
        self.residuals = {}
        for scan in self.scans:
            values = self.rng.normal(size=(100, 3))
            self.residuals[scan["scan_id"]] = values
            axis = BrainModelAxis.from_mask(np.ones(3, dtype=bool), name="CortexLeft")
            path = derivative_path(self.config, scan, "xcpd", "space-fsLR_den-91k_desc-denoised_bold.dtseries.nii")
            path.parent.mkdir(parents=True, exist_ok=True)
            nib.save(nib.Cifti2Image(values, header=nib.Cifti2Header.from_axes((SeriesAxis(0, 2, 100), axis))), path)
            parcels = ParcelsAxis(["a", "b", "c"], [np.empty((0, 3), dtype=int)] * 3, [{}] * 3)
            path = derivative_path(self.config, scan, "xcpd", "space-fsLR_atlas-synthetic_den-91k_stat-mean_timeseries.ptseries.nii")
            nib.save(nib.Cifti2Image(values, header=nib.Cifti2Header.from_axes((SeriesAxis(0, 2, 100), parcels))), path)
            columns, custom = self.custom_values[scan["scan_id"]]
            motion = [c + "_filtered" if c.startswith(("rot_", "trans_")) else c for c in self.confounds_columns]
            with derivative_path(self.config, scan, "xcpd", "design.tsv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream, delimiter="\t")
                writer.writerow([*motion, *columns])
                writer.writerows(np.column_stack([self.rng.normal(size=(100, 36)), custom]))

    def finish_xcpd(self):
        start_container(self.config, "xcpd", self.subject, self.scans)
        self.write_outputs()
        with patch("imaging.pipeline.subprocess.check_output", return_value="synthetic"):
            finish_container(self.config, "xcpd", self.subject, self.scans, ["mock"], "mock-xcpd")

    def test_paths_full_upstream_and_exact_filters(self):
        self.assertEqual(len(self.scans), 2)
        original = (module_path(self.config, "fmriprep", "logs") / "input_scans.csv").read_bytes()
        assert_completed(self.config, "fmriprep", self.subject, self.scans)
        logs = module_path(self.config, "xcpd", "logs")
        self.assertEqual(logs.parts[-2:], ("task_background", "nback"))
        self.assertEqual(json.loads((logs / "filters" / f"{self.subject}.json").read_text()),
                         {"bold": {"task": "nback", "run": [1, 10]}})
        self.config["task"] = "sst"
        prepare_background(self.config, self.upstream, None)
        scans = background_scans(self.config)
        self.assertEqual(len(scans), 1)
        self.assertTrue(inspect_confounds(self.config, scans[0])["ready"])
        self.assertEqual(json.loads((module_path(self.config, "xcpd", "logs") / "filters" / f"{self.subject}.json").read_text()),
                         {"bold": {"task": "sst", "run": None}})
        self.assertEqual(original, (module_path(self.config, "fmriprep", "logs") / "input_scans.csv").read_bytes())
        shell = io.StringIO()
        with redirect_stdout(shell):
            shell_config(self.config, "xcpd", self.subject)
        self.assertIn("work_task_background/sst/", shell.getvalue())
        self.assertIn("fmriprep/THU/task", shell.getvalue())
        settings = processing_settings(self.config, "fmriprep")
        self.config["task_xcpd"]["confounds_dir"] = "another-source"
        self.assertEqual(settings, processing_settings(self.config, "fmriprep"))

    def test_switch_and_constant_or_missing_36p_are_explicit(self):
        self.config["task"] = "switch"
        prepare_background(self.config, self.upstream, None)
        scan = background_scans(self.config)[0]
        self.assertTrue(inspect_confounds(self.config, scan)["ready"])
        path = self.custom_file(scan)
        with path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.reader(stream, delimiter="\t"))
        for row in rows[1:]:
            row[0] = "0"
        with path.open("w", encoding="utf-8", newline="") as stream:
            csv.writer(stream, delimiter="\t").writerows(rows)
        self.assertIn("constant", ";".join(inspect_confounds(self.config, scan)["issues"]))
        preproc = derivative_path(self.config, scan, "fmriprep", "desc-confounds_timeseries.tsv")
        content = preproc.read_text().replace("trans_x\t", "not_motion\t")
        preproc.write_text(content, encoding="utf-8")
        self.assertIn("lack 36P", ";".join(inspect_confounds(self.config, scan)["issues"]))

    def test_scientific_mismatches_block_submission(self):
        metadata_file = self.custom_file(self.scans[0]).with_suffix(".json")
        original = json.loads(metadata_file.read_text())
        for field, wrong, reason in (("FrameTimeOffsetSeconds", 0, "STC"), ("RepetitionTime", 3, "TR"),
                                     ("NFrames", 99, "frame count"), ("SourceBOLD", "/other.nii.gz", "SourceBOLD"),
                                     ("DummyVolumesRemovedHere", 1, "dummy")):
            metadata = json.loads(json.dumps(original))
            metadata["TaskDesignProvenance"][field] = wrong
            metadata_file.write_text(json.dumps(metadata), encoding="utf-8")
            audit = inspect_confounds(self.config, self.scans[0])
            self.assertFalse(audit["ready"])
            self.assertIn(reason, ";".join(audit["issues"]))
            with patch("imaging.pipeline.subprocess.check_output") as sbatch:
                with self.assertRaisesRegex(AssertionError, "not ready"):
                    submit(self.config, "xcpd", REPO / "configs/neuroimaging_stc.json", self.scans, None, True)
                sbatch.assert_not_called()
        metadata_file.write_text(json.dumps(original), encoding="utf-8")
        self.custom_file(self.scans[0]).unlink()
        prepare_background(self.config, self.upstream, None)
        audit = read_csv(module_path(self.config, "xcpd", "tables") / "input_readiness.csv")[0]
        self.assertEqual(audit["runs"], "2")
        self.assertEqual(audit["ready_runs"], "1")
        self.assertEqual(audit["ready"], "False")

    def test_invalid_numeric_and_column_semantics_are_not_imputed(self):
        path = self.custom_file(self.scans[0])
        original = path.read_text()
        path.write_text(original.replace("task_0back", "signal__task_0back"), encoding="utf-8")
        self.assertIn("unexpected", ";".join(inspect_confounds(self.config, self.scans[0])["issues"]))
        lines = original.splitlines()
        cells = lines[1].split("\t")
        cells[0] = "nan"
        lines[1] = "\t".join(cells)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.assertIn("non-finite", ";".join(inspect_confounds(self.config, self.scans[0])["issues"]))

    def test_changed_design_invalidates_prepared_and_completed_inputs(self):
        self.finish_xcpd()
        assert_completed(self.config, "xcpd", self.subject, self.scans)
        path = self.custom_file(self.scans[0])
        lines = path.read_text().splitlines()
        cells = lines[1].split("\t")
        cells[0] = str(float(cells[0]) + 1)
        lines[1] = "\t".join(cells)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(AssertionError, "changed"):
            assert_completed(self.config, "xcpd", self.subject, self.scans)
        prepare_background(self.config, self.upstream, None)
        validate_background_inputs(self.config, self.scans)
        path = derivative_path(self.config, self.scans[0], "fmriprep", "desc-confounds_timeseries.tsv")
        lines = path.read_text().splitlines()
        cells = lines[1].split("\t")
        cells[0] = str(float(cells[0]) + 1)
        lines[1] = "\t".join(cells)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(AssertionError, "changed"):
            validate_background_inputs(self.config, self.scans)

    def test_task_changes_during_run_cannot_be_registered(self):
        start_container(self.config, "xcpd", self.subject, self.scans)
        self.write_outputs()
        path = self.custom_file(self.scans[0]).with_suffix(".json")
        metadata = json.loads(path.read_text())
        metadata["TaskDesignProvenance"]["SourceCSV"] = "new-task-source.csv"
        path.write_text(json.dumps(metadata), encoding="utf-8")
        prepare_background(self.config, self.upstream, None)
        with self.assertRaisesRegex(AssertionError, "changed during"):
            finish_container(self.config, "xcpd", self.subject, self.scans, ["mock"], "mock")
        self.assertFalse(record_path(self.config, "xcpd", self.subject).exists())

    def test_joint_design_and_independent_run_fc(self):
        self.finish_xcpd()
        compute_background_fc(self.config, self.scans, self.subject)
        validate_background_fc(self.config, self.scans)
        for scan in self.scans:
            path = module_path(self.config, "background_fc", "processed") / self.subject / scan["scan_id"] / (
                f"synthetic/raw/{scan['scan_id']}_atlas-synthetic_fc.csv")
            matrix = np.loadtxt(path, delimiter=",", skiprows=1, usecols=(1, 2, 3))
            np.testing.assert_allclose(matrix, np.corrcoef(self.residuals[scan["scan_id"]], rowvar=False))
        summary = read_csv(module_path(self.config, "background_fc", "tables") / "subjects" / f"{self.subject}.csv")
        self.assertEqual(len(summary), 2)
        self.assertNotIn("ptseries", summary[0])
        compute_motion(self.config, self.scans, self.subject)
        motion = read_csv(module_path(self.config, "head_motion", "tables") / "subjects" / f"{self.subject}.csv")
        self.assertNotIn("source_bold", motion[0])
        self.assertNotIn("subject_valid", motion[0])
        design = derivative_path(self.config, self.scans[0], "xcpd", "design.tsv")
        design.write_text(design.read_text().replace("task_0back", "signal__task_0back"), encoding="utf-8")
        with self.assertRaisesRegex(AssertionError, "joint design"):
            validate_joint_design(self.config, self.scans)

    def test_consistently_wrong_residual_tr_is_rejected(self):
        self.write_outputs()
        scan = self.scans[0]
        for suffix in ("space-fsLR_den-91k_desc-denoised_bold.dtseries.nii",
                       "space-fsLR_atlas-synthetic_den-91k_stat-mean_timeseries.ptseries.nii"):
            path = derivative_path(self.config, scan, "xcpd", suffix)
            image = nib.load(path, mmap=False)
            wrong = nib.Cifti2Image(image.get_fdata(), header=nib.Cifti2Header.from_axes(
                (SeriesAxis(0, 3, 100), image.header.get_axis(1))))
            nib.save(wrong, path)
        with self.assertRaisesRegex(AssertionError, "Task residual TR differs"):
            validate_time_axes(self.config, "xcpd", [scan])

    def test_submission_routes_and_upstream_completion(self):
        with patch("imaging.pipeline.subprocess.check_output", return_value="12345\n") as sbatch:
            submit(self.config, "xcpd", REPO / "configs/neuroimaging_stc.json", self.scans, None, False)
            command = sbatch.call_args.args[0]
            self.assertEqual(command[-1], "nback")
            self.assertIn("run_xcpd_task_background.sbatch", " ".join(command))
            self.assertEqual(command[command.index("--cpus-per-task") + 1], "1")
        with patch("imaging.pipeline.subprocess.run") as run:
            run_stage(self.config, "xcpd", self.subject, self.scans, True)
            command = run.call_args.args[0]
            self.assertTrue(command[1].endswith("run_xcpd_task_background.sbatch"))
            self.assertEqual(command[-2:], ["nback", "--dry-run"])

    @unittest.skipUnless(BASH, "Set EFNY_TEST_BASH to a native Bash on Windows")
    def test_shell_command_and_mocked_completion(self):
        self.write_outputs()
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        stubs = {
            "uv": '#!/usr/bin/env bash\nif [[ "$1" == sync ]]; then exit 0; fi\nshift 3\nshift\nexec "$TEST_PYTHON" -m imaging.pipeline "$@"\n',
            "module": '#!/usr/bin/env bash\nexit 0\n',
            "singularity": '#!/usr/bin/env bash\n[[ "$SINGULARITYENV_HTTP_PROXY" == "http://10.11.100.5:3128" ]] || exit 91\nif [[ "${@: -1}" == --version ]]; then printf "mock-container\\n"; fi\n',
        }
        for name, text in stubs.items():
            p = fake_bin / name
            p.write_text(text, encoding="utf-8", newline="\n")
            p.chmod(0o755)
        wrapper = self.root / "wrapper.sh"
        wrapper.write_text('#!/usr/bin/env bash\nexport PATH="$(cd "$TEST_BIN" && pwd):$PATH"\nexec bash "$@"\n', encoding="utf-8", newline="\n")
        config_file = self.root / "config.json"
        config_file.write_text(json.dumps(self.config), encoding="utf-8")
        env = dict(os.environ, TEST_BIN=fake_bin.as_posix(), TEST_PYTHON=Path(sys.executable).as_posix(),
                   SLURM_SUBMIT_DIR=self.root.as_posix(), MSYS2_ARG_CONV_EXCL="*")
        env.pop("SLURM_CPUS_PER_TASK", None)
        args = [BASH, wrapper.as_posix(), (REPO / "scripts/neuroimaging/run_xcpd_task_background.sbatch").as_posix(),
                "THU", self.subject, config_file.as_posix(), self.root.as_posix(), "nback"]
        preview = subprocess.run([*args, "--dry-run"], env=env, capture_output=True, text=True, check=True)
        import shlex
        command = shlex.split(preview.stdout.strip())
        self.assertEqual(command[command.index("--task-id") + 1], "nback")
        self.assertEqual(command[command.index("--datasets") + 1], "custom=/custom_confounds")
        self.assertEqual(command.count("--datasets"), 1)
        self.assertIn(str(Path(self.config["task_xcpd"]["confounds_dir"]).as_posix()) + ":/custom_confounds:ro", command)
        self.assertEqual(command[command.index("--nuisance-regressors") + 1], "/task_confounds.yml")
        execution = subprocess.run(args, env=env, capture_output=True, text=True)
        self.assertEqual(execution.returncode, 0, execution.stderr)
        record = assert_completed(self.config, "xcpd", self.subject, self.scans)
        self.assertEqual(record["command"], command)
        check(self.config, "xcpd", self.scans)
        with patch("imaging.pipeline.subprocess.check_output", return_value="synthetic"):
            run_stage(self.config, "background_fc", self.subject, self.scans, False)
        check(self.config, "background_fc", self.scans)
        self.assertTrue(record_path(self.config, "background_fc", self.subject).exists())


if __name__ == "__main__":
    unittest.main()
