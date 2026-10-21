"""Synthetic scientific checks; all temporary images stay under temp/smoke_* and are removed."""

import io
import json
import os
import shlex
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

from imaging.config import load_config, module_path, shell_config
from imaging.pipeline import (
    assert_completed, assert_qc_current, check, discover_scans, finish_container, input_scans, prepare,
    processing_settings, record_path, start_container, submit,
)
from imaging.rest import (
    compute_fc, compute_motion, derivative_path, load_ptseries, read_csv, summarize_qc,
    write_motion_qc_tables,
)


REPO = Path(__file__).resolve().parents[1]
BASH = os.environ.get("EFNY_TEST_BASH") if os.name == "nt" else shutil.which("bash")


class NeuroimagingTests(unittest.TestCase):
    def setUp(self):
        temp = REPO / "temp"
        temp.mkdir(exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix="smoke_neuroimaging_", dir=temp))
        self.config = load_config(REPO / "configs/neuroimaging.json", "THU", self.root)
        self.config["bids_dir"] = str(self.root / "bids")
        self.config["datasets"]["THU"]["bids_dir"] = self.config["bids_dir"]
        self.arrays = {}
        rng = np.random.default_rng(42)
        for subject in ("sub-THU0001", "sub-THU0002"):
            for run in (1, 10):
                path = self.root / "bids" / subject / "func" / f"{subject}_task-rest_run-{run}_bold.nii.gz"
                path.parent.mkdir(parents=True, exist_ok=True)
                nib.save(nib.Nifti1Image(np.zeros((2, 2, 2, 12)), np.eye(4)), path)
        self.scans = discover_scans(self.config, None)
        for scan in self.scans:
            confounds = derivative_path(self.config, scan, "fmriprep", "desc-confounds_timeseries.tsv")
            confounds.parent.mkdir(parents=True, exist_ok=True)
            confounds.write_text("framewise_displacement\nn/a\n" + "0.1\n" * 11, encoding="utf-8")
            for stage, suffix in (
                ("fmriprep", "space-fsLR_den-91k_bold.dtseries.nii"),
                ("xcpd", "space-fsLR_den-91k_desc-denoised_bold.dtseries.nii"),
            ):
                path = derivative_path(self.config, scan, stage, suffix)
                path.parent.mkdir(parents=True, exist_ok=True)
                axis = BrainModelAxis.from_mask(np.ones(3, dtype=bool), name="CortexLeft")
                nib.save(nib.Cifti2Image(rng.normal(size=(12, 3)), header=nib.Cifti2Header.from_axes((SeriesAxis(0, 2, 12), axis))), path)
            mni = derivative_path(self.config, scan, "fmriprep", "space-MNI152NLin2009cAsym_desc-preproc_bold.nii.gz")
            nib.save(nib.Nifti1Image(np.zeros((2, 2, 2, 12)), np.eye(4)), mni)
            for atlas, parcels in self.config["atlases"].items():
                data = rng.normal(size=(12, parcels)) * int(scan["run"]) + int(scan["run"])
                self.arrays[(scan["scan_id"], atlas)] = data
                self.write_ptseries(scan, atlas, data)
        for stage in ("fmriprep", "xcpd"):
            root = module_path(self.config, stage, "interim")
            (root / "dataset_description.json").write_text('{"DatasetType":"derivative"}', encoding="utf-8")
            for subject in ("sub-THU0001", "sub-THU0002"):
                (root / f"{subject}.html").write_text("synthetic report", encoding="utf-8")

    def tearDown(self):
        assert self.root.resolve().is_relative_to((REPO / "temp").resolve())
        shutil.rmtree(self.root)

    def write_ptseries(self, scan, atlas, data, reverse=False, transpose=False):
        labels = [f"parcel_{i}" for i in range(data.shape[1])]
        if reverse:
            labels.reverse()
        parcels = ParcelsAxis(labels, [np.zeros((0, 3), dtype=int)] * len(labels), [{} for _ in labels])
        time = SeriesAxis(0, 2, data.shape[0])
        axes = (parcels, time) if transpose else (time, parcels)
        path = derivative_path(self.config, scan, "xcpd", f"space-fsLR_atlas-{atlas}_den-91k_stat-mean_timeseries.ptseries.nii")
        nib.save(nib.Cifti2Image(data.T if transpose else data, header=nib.Cifti2Header.from_axes(axes)), path)
        return path

    def motion_qc(self):
        for subject in ("sub-THU0001", "sub-THU0002"):
            compute_motion(self.config, self.scans, subject)
        summarize_qc(self.config, self.scans)

    def test_default_paths_and_unconfigured_xy(self):
        config = load_config(REPO / "configs/neuroimaging.json", "THU")
        self.assertEqual(config["bids_dir"], "/ibmgpfs/cuizaixu_lab/liyang/BrainProject25/Tsinghua_data/BIDS_new")
        self.assertEqual(config["project_root"], "/ibmgpfs/cuizaixu_lab/xuhaoshu/projects/efny-pipeline")
        self.assertEqual(config["head_motion"]["min_valid_runs"], 2)
        with self.assertRaises(ValueError):
            load_config(REPO / "configs/neuroimaging.json", "XY")

    def test_numeric_run_order_and_reject_sessions(self):
        self.assertEqual([scan["run"] for scan in self.scans[:2]], ["1", "10"])
        (self.root / "bids/sub-THU0001/ses-01").mkdir()
        with self.assertRaisesRegex(AssertionError, "Session"):
            discover_scans(self.config, None)

    def test_no_slicetiming_isolates_products_caches_and_downstream_inputs(self):
        for module, kind in (("fmriprep", "interim"), ("xcpd", "interim"),
                             ("head_motion", "tables"), ("rest_fc", "processed"),
                             ("fmriprep", "logs"), ("fmriprep", "temp")):
            path = module_path(self.config, module, kind)
            self.assertEqual(path.parts[-4:], (module, "THU", "no_slicetiming", "rest"))
        stream = io.StringIO()
        with redirect_stdout(stream):
            shell_config(self.config, "xcpd", "sub-THU0001")
        values = dict(line.split("=", 1) for line in stream.getvalue().splitlines())
        self.assertEqual(shlex.split(values["FMRIPREP_DIR"])[0],
                         module_path(self.config, "fmriprep", "interim").as_posix())
        for name in ("OUTPUT_DIR", "WORK_DIR", "TEMP_DIR", "LOG_DIR", "FREESURFER_DIR"):
            self.assertIn("/THU/no_slicetiming/", shlex.split(values[name])[0] + "/")
        no_stc_record = record_path(self.config, "fmriprep", "sub-THU0001")
        self.config["fmriprep"]["ignore"] = []
        self.assertEqual(module_path(self.config, "fmriprep", "interim"),
                         self.root / "data/interim/neuroimaging/fmriprep/THU/rest")
        self.assertNotEqual(record_path(self.config, "fmriprep", "sub-THU0001"), no_stc_record)

    def test_missing_run_is_an_error(self):
        source = Path(self.scans[0]["source_bold"])
        source.rename(source.with_name(source.name.replace("_run-1", "")))
        with self.assertRaises(KeyError):
            discover_scans(self.config, None)

    def test_stc_primary_config_preserves_parameters_and_legacy_rest_settings(self):
        config = load_config(REPO / "configs/neuroimaging_stc.json", "THU", self.root)
        self.assertEqual(config["fmriprep"]["ignore"], [])
        self.assertEqual(config["task_fmri"]["tasks"], ["sst", "nback", "switch"])
        for key in self.config:
            if key in ("fmriprep", "bids_dir", "datasets"):
                continue
            self.assertEqual(config[key], self.config[key])
        self.assertEqual({k:v for k,v in config["fmriprep"].items() if k != "ignore"},
                         {k:v for k,v in self.config["fmriprep"].items() if k != "ignore"})
        self.assertNotIn("ignore", processing_settings(config, "fmriprep")["fmriprep"])
        self.assertEqual(module_path(config, "fmriprep", "interim"),
                         self.root / "data/interim/neuroimaging/fmriprep/THU/rest")

    def test_task_inventory_requires_stc_and_keeps_missing_run_entity(self):
        config = load_config(REPO / "configs/neuroimaging_stc.json", "THU", self.root, "task")
        config["bids_dir"] = self.config["bids_dir"]
        selected = self.root / "task_subjects.txt"
        selected.write_text("sub-THU0001\n", encoding="utf-8")
        for task in ("sst", "nback"):
            path = self.root / "bids/sub-THU0001/func" / f"sub-THU0001_task-{task}_bold.nii.gz"
            nib.save(nib.Nifti1Image(np.zeros((2,2,2,12)), np.eye(4)), path)
            path.with_name(path.name.removesuffix(".nii.gz") + ".json").write_text(
                json.dumps(dict(RepetitionTime=2, SliceTiming=[0,1])), encoding="utf-8")
        scans = discover_scans(config, selected)
        self.assertEqual([r["task"] for r in scans], ["nback", "sst"])
        self.assertEqual([r["run"] for r in scans], ["", ""])
        prepare(config, selected)
        logs = module_path(config, "fmriprep", "logs")
        self.assertEqual(json.loads((logs / "bids_filter.json").read_text()),
                         {"bold":{"task":["sst","nback","switch"]}})
        preview = io.StringIO()
        with redirect_stdout(preview):
            submit(config, "fmriprep", REPO / "configs/neuroimaging_stc.json", scans, None, True)
        self.assertIn("run_fmriprep_task.sbatch", preview.getvalue())
        stream = io.StringIO()
        with redirect_stdout(stream):
            shell_config(config, "fmriprep", "sub-THU0001")
        values = dict(line.split("=",1) for line in stream.getvalue().splitlines())
        self.assertTrue(shlex.split(values["OUTPUT_DIR"])[0].endswith("/fmriprep/THU/task"))
        self.assertIn("/work_task/", shlex.split(values["WORK_DIR"])[0])
        self.assertTrue(shlex.split(values["FREESURFER_DIR"])[0].endswith("/freesurfer/THU"))
        bad = self.root / "bids/sub-THU0001/func/sub-THU0001_task-sst_bold.json"
        bad.write_text('{"RepetitionTime":2}', encoding="utf-8")
        with self.assertRaisesRegex(AssertionError, "STC requires SliceTiming"):
            discover_scans(config, selected)

    def test_fd_reference_denominator_and_no_missing_interior(self):
        scan = self.scans[0]
        path = derivative_path(self.config, scan, "fmriprep", "desc-confounds_timeseries.tsv")
        path.write_text("framewise_displacement\nn/a\n0.4\n" + "0.1\n" * 10, encoding="utf-8")
        compute_motion(self.config, self.scans, scan["subject"])
        row = read_csv(module_path(self.config, "head_motion", "tables") / "subjects/sub-THU0001.csv")[0]
        self.assertAlmostEqual(float(row["mean_fd_mm"]), 1.4 / 11)
        self.assertAlmostEqual(float(row["high_motion_ratio"]), 1 / 12)
        self.assertEqual(int(row["fd_valid_frames"]), 11)
        path.write_text("framewise_displacement\nn/a\nnan\n" + "0.1\n" * 10, encoding="utf-8")
        with self.assertRaisesRegex(AssertionError, "Invalid FD"):
            compute_motion(self.config, self.scans, scan["subject"])

    def test_volume_mismatch_is_an_error(self):
        path = derivative_path(self.config, self.scans[0], "fmriprep", "desc-confounds_timeseries.tsv")
        path.write_text("framewise_displacement\nn/a\n0.1\n", encoding="utf-8")
        with self.assertRaisesRegex(AssertionError, "volume mismatch"):
            compute_motion(self.config, self.scans, "sub-THU0001")

    def test_qc_minimum_two_and_dataset_specific_iqr(self):
        path = derivative_path(self.config, self.scans[1], "fmriprep", "desc-confounds_timeseries.tsv")
        path.write_text("framewise_displacement\nn/a\n" + "0.8\n" * 11, encoding="utf-8")
        self.motion_qc()
        rows = read_csv(module_path(self.config, "head_motion", "tables") / "subject_qc.csv")
        self.assertEqual(rows[0]["subject_valid"], "false")
        self.assertEqual(rows[1]["subject_valid"], "true")
        self.assertEqual(rows[0]["rest1_valid"], "true")
        self.assertEqual(rows[0]["rest10_valid"], "false")
        self.assertEqual(float(rows[0]["rest10_fd"]), 0.8)
        with self.assertRaisesRegex(AssertionError, "failed QC"):
            compute_fc(self.config, self.scans, "sub-THU0001")

    def test_wide_qc_preserves_run_identity_and_absence(self):
        self.motion_qc()
        root = module_path(self.config, "head_motion", "tables")
        runs = read_csv(root / "run_qc.csv")
        runs = [row for row in runs if not (row["subject"] == "sub-THU0002" and row["run"] == "10")]
        write_motion_qc_tables(self.config, runs)
        subjects = read_csv(root / "subject_qc.csv")
        self.assertEqual(subjects[0]["rest10_fd"], runs[1]["mean_fd_mm"])
        self.assertEqual(subjects[1]["rest10_valid"], "")
        self.assertEqual(subjects[1]["valid_runs"], "1")
        self.assertEqual(subjects[1]["subject_valid"], "false")
        self.assertNotIn("source_bold", read_csv(root / "run_qc.csv")[0])
        self.assertNotIn("confounds", subjects[0])
        with self.assertRaisesRegex(AssertionError, "Duplicate subject/run"):
            write_motion_qc_tables(self.config, runs + [runs[0]])

    def test_fc_matches_concatenation_with_raw_run_amplitudes(self):
        self.motion_qc()
        compute_fc(self.config, self.scans, "sub-THU0001")
        atlas = "4S156Parcels"
        values = np.concatenate([self.arrays[(row["scan_id"], atlas)] for row in self.scans[:2]])
        expected = np.corrcoef(values, rowvar=False)
        path = module_path(self.config, "rest_fc", "processed") / f"sub-THU0001/{atlas}/raw/sub-THU0001_atlas-{atlas}_fc.csv"
        actual = np.loadtxt(path, delimiter=",", skiprows=1, usecols=range(1, 157))
        np.testing.assert_allclose(actual, expected, atol=1e-12)
        zpath = path.parent.parent / "fisher_z/sub-THU0001_atlas-4S156Parcels_fc_fisher_z.csv"
        z = np.loadtxt(zpath, delimiter=",", skiprows=1, usecols=range(1, 157))
        expected_z = np.arctanh(np.clip(expected, -0.999999, 0.999999))
        np.fill_diagonal(expected_z, 0)
        np.testing.assert_allclose(z, expected_z, atol=1e-12)

    def test_cifti_orientation_and_no_nan_or_constant_imputation(self):
        scan = self.scans[0]
        atlas = "4S156Parcels"
        data = self.arrays[(scan["scan_id"], atlas)].copy()
        path = self.write_ptseries(scan, atlas, data, transpose=True)
        actual, _, tr = load_ptseries(path, 156)
        np.testing.assert_array_equal(actual, data)
        self.assertEqual(tr, 2)
        data[0, 0] = np.nan
        self.write_ptseries(scan, atlas, data)
        with self.assertRaisesRegex(AssertionError, "Non-finite"):
            load_ptseries(path, 156)
        data[:, 0] = 0
        self.write_ptseries(scan, atlas, data)
        with self.assertRaisesRegex(AssertionError, "Constant"):
            load_ptseries(path, 156)

    def test_parcel_order_and_time_window_mismatch(self):
        self.motion_qc()
        scan = self.scans[1]
        atlas = "4S156Parcels"
        data = self.arrays[(scan["scan_id"], atlas)]
        self.write_ptseries(scan, atlas, data, reverse=True)
        with self.assertRaisesRegex(AssertionError, "Parcel order"):
            compute_fc(self.config, self.scans, "sub-THU0001")
        self.write_ptseries(scan, atlas, data[:-1])
        with self.assertRaisesRegex(AssertionError, "time window"):
            compute_fc(self.config, self.scans, "sub-THU0001")

    def test_submission_preview(self):
        output = io.StringIO()
        with redirect_stdout(output):
            submit(self.config, "fmriprep", REPO / "configs/neuroimaging.json", self.scans, None, True)
        self.assertEqual(output.getvalue().count("sbatch --parsable"), 1)
        self.assertIn("--array 0-1%48", output.getvalue())
        self.assertIn("--cpus-per-task 6", output.getvalue())
        self.assertIn("--partition q_fat_c ", output.getvalue())
        self.assertNotIn("--time", output.getvalue())
        self.assertNotIn("--mem", output.getvalue())
        self.assertFalse(module_path(self.config, "fmriprep", "logs").exists())

    def test_array_submission_freezes_subject_order_and_receipts(self):
        scans = [dict(self.scans[0], subject=f"sub-THU{index:04d}") for index in range(49)]
        with patch("imaging.pipeline.subprocess.check_output", return_value="12345;cluster\n") as sbatch:
            submit(self.config, "fmriprep", REPO / "configs/neuroimaging.json", scans, None, False)
        sbatch.assert_called_once()
        command = sbatch.call_args.args[0]
        self.assertEqual(command[command.index("--array") + 1], "0-48%48")
        frozen = Path(command[-1])
        self.assertEqual(frozen.read_text(encoding="utf-8").splitlines(), [scan["subject"] for scan in scans])
        receipts = read_csv(next(module_path(self.config, "fmriprep", "logs").glob("submitted_*.csv")))
        self.assertEqual([row["job_id"] for row in receipts], [f"12345_{index}" for index in range(49)])
        self.assertEqual([row["subject"] for row in receipts], frozen.read_text(encoding="utf-8").splitlines())
        subset = self.root / "selected.txt"
        subset.write_text("sub-THU0002\nsub-THU0001\n", encoding="utf-8")
        with patch("imaging.pipeline.subprocess.check_output", return_value="12346\n") as sbatch:
            submit(self.config, "fmriprep", REPO / "configs/neuroimaging.json", scans, subset, False)
        frozen_subset = Path(sbatch.call_args.args[0][-1])
        subset.write_text("sub-THU0000\n", encoding="utf-8")
        self.assertEqual(frozen_subset.read_text(encoding="utf-8"), "sub-THU0002\nsub-THU0001\n")

    def test_completion_tracks_reruns_and_missing_products(self):
        prepare(self.config, None)
        scans = input_scans(self.config)
        with patch("imaging.pipeline.subprocess.check_output", return_value="synthetic-version"):
            for stage in ("fmriprep", "xcpd"):
                start_container(self.config, stage, "sub-THU0001", scans)
                finish_container(self.config, stage, "sub-THU0001", scans, ["singularity", stage], "synthetic-version")
        assert_completed(self.config, "xcpd", "sub-THU0001", scans)
        check(self.config, "xcpd", scans)
        audit = read_csv(module_path(self.config, "xcpd", "logs") / "completion_audit.csv")
        self.assertEqual(audit[0]["complete"], "true")
        self.assertEqual(audit[1]["complete"], "false")
        marker = record_path(self.config, "fmriprep", "sub-THU0001")
        record = json.loads(marker.read_text(encoding="utf-8"))
        record["completed_at_utc"] = "later-rerun"
        marker.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaisesRegex(AssertionError, "was rerun"):
            assert_completed(self.config, "xcpd", "sub-THU0001", scans)

    @unittest.skipUnless(BASH, "Set EFNY_TEST_BASH to a native Bash executable on Windows")
    def test_shell_commands_and_completion_with_mocked_containers(self):
        prepare(self.config, None)
        config_path = self.root / "config.json"
        config_path.write_text(json.dumps(self.config), encoding="utf-8")
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        stubs = {
            "uv": '#!/usr/bin/env bash\nif [[ "$1" == sync ]]; then exit 0; fi\nshift 3\n[[ "$1" == efny-imaging ]] || exit 2\nshift\nexec "$TEST_PYTHON" -m imaging.pipeline "$@"\n',
            "module": '#!/usr/bin/env bash\nexit 0\n',
            "singularity": (
                '#!/usr/bin/env bash\n'
                'for variable in http_proxy HTTP_PROXY https_proxy HTTPS_PROXY ftp_proxy FTP_PROXY all_proxy ALL_PROXY '
                'SINGULARITYENV_http_proxy SINGULARITYENV_HTTP_PROXY SINGULARITYENV_https_proxy SINGULARITYENV_HTTPS_PROXY '
                'SINGULARITYENV_ftp_proxy SINGULARITYENV_FTP_PROXY SINGULARITYENV_all_proxy SINGULARITYENV_ALL_PROXY; do\n'
                '    [[ "${!variable}" == "http://10.11.100.5:3128" ]] || exit 91\n'
                'done\n'
                '[[ " $* " == *":/templateflow:ro "* ]] || exit 92\n'
                'if [[ "${@: -1}" == --version ]]; then printf "mock-container\\n"; fi\n'
            ),
        }
        for name, content in stubs.items():
            path = fake_bin / name
            path.write_text(content, encoding="utf-8")
            path.chmod(0o755)
        environment = dict(os.environ)
        environment.pop("SLURM_CPUS_PER_TASK", None)
        environment.update(TEST_PYTHON=Path(sys.executable).as_posix(),
                           SLURM_SUBMIT_DIR=self.root.as_posix(), MSYS2_ARG_CONV_EXCL="*")
        # Set PATH inside Bash so the same stubs work on Linux and Git Bash for Windows.
        wrapper = self.root / "test_stage.sh"
        wrapper.write_text('#!/usr/bin/env bash\nexport PATH="$(cd "$TEST_BIN" && pwd):$PATH"\nexec bash "$@"\n', encoding="utf-8")
        environment["TEST_BIN"] = fake_bin.as_posix()
        for stage in ("fmriprep", "xcpd"):
            arguments = [BASH, wrapper.as_posix(), (REPO / f"scripts/neuroimaging/run_{stage}.sbatch").as_posix(),
                         "THU", "sub-THU0001", config_path.as_posix(), self.root.as_posix()]
            preview = subprocess.run([*arguments, "--dry-run"], env=environment, text=True, capture_output=True, check=True)
            command = shlex.split(preview.stdout.strip())
            self.assertEqual(command[command.index("--nprocs") + 1], "6" if stage == "fmriprep" else "1")
            self.assertEqual(command[command.index("--omp-nthreads") + 1], "6" if stage == "fmriprep" else "1")
            if stage == "fmriprep":
                self.assertIn((self.root / "bids").as_posix() + ":/BIDS:ro", command)
                self.assertIn("--skip-bids-validation", command)
                self.assertEqual(command[command.index("--ignore") + 1:], ["slicetiming"])
                self.assertIn(module_path(self.config, stage, "interim").as_posix() + ":/output:rw", command)
            else:
                self.assertIn(module_path(self.config, "fmriprep", "interim").as_posix() + ":/fmriprep:ro", command)
                self.assertEqual(command[command.index("--fd-thresh") + 1], "0")
                self.assertEqual(command[command.index("--nuisance-regressors") + 1], "36P")
            execution = subprocess.run(arguments, env=environment, text=True, capture_output=True)
            self.assertEqual(execution.returncode, 0, execution.stderr)
            record = assert_completed(self.config, stage, "sub-THU0001", self.scans)
            self.assertEqual(record["command"], command)
            self.assertFalse((module_path(self.config, stage, "logs") / "locks/sub-THU0001.lock").exists())

        # A reversed frozen list must select its first subject for array task zero.
        frozen = self.root / "array_subjects.txt"
        frozen.write_text("sub-THU0002\nsub-THU0001\n", encoding="utf-8", newline="\n")
        array_arguments = [BASH, wrapper.as_posix(), (REPO / "scripts/neuroimaging/run_fmriprep.sbatch").as_posix(),
                           "THU", "--array", config_path.as_posix(), self.root.as_posix(), frozen.as_posix()]
        array_environment = dict(environment, SLURM_ARRAY_TASK_ID="0", SLURM_JOB_ID="12345")
        execution = subprocess.run(array_arguments, env=array_environment, text=True, capture_output=True)
        error_log = module_path(self.config, "fmriprep", "logs") / "sub-THU0002_12345.err"
        self.assertEqual(execution.returncode, 0, execution.stderr + error_log.read_text(encoding="utf-8"))
        record = assert_completed(self.config, "fmriprep", "sub-THU0002", self.scans)
        self.assertEqual(record["job_id"], "12345")
        self.assertEqual(record["command"][record["command"].index("--participant-label") + 1], "THU0002")
        subject_log = module_path(self.config, "fmriprep", "logs") / "sub-THU0002_12345.out"
        self.assertIn("--ignore slicetiming", subject_log.read_text(encoding="utf-8"))

        # The task worker uses the same scientific settings, selects task BOLD, and retains STC.
        task_config = json.loads(json.dumps(self.config))
        task_config.update(scope="task", task_fmri={"tasks":["sst","nback","switch"]})
        task_config["fmriprep"]["ignore"] = []
        task_source = self.root / "bids/sub-THU0001/func/sub-THU0001_task-sst_bold.nii.gz"
        shutil.copyfile(self.scans[0]["source_bold"], task_source)
        task_source.with_name("sub-THU0001_task-sst_bold.json").write_text(
            '{"RepetitionTime":2,"SliceTiming":[0,1]}', encoding="utf-8")
        selected = self.root / "task_subjects.txt"
        selected.write_text("sub-THU0001\n", encoding="utf-8")
        prepare(task_config, selected)
        task_scans = input_scans(task_config)
        task_root = module_path(task_config, "fmriprep", "interim")
        task_root.mkdir(parents=True)
        (task_root / "dataset_description.json").write_text('{"DatasetType":"derivative"}', encoding="utf-8")
        (task_root / "sub-THU0001.html").write_text("synthetic task report", encoding="utf-8")
        for suffix in ("space-fsLR_den-91k_bold.dtseries.nii",
                       "space-MNI152NLin2009cAsym_desc-preproc_bold.nii.gz", "desc-confounds_timeseries.tsv"):
            dest = derivative_path(task_config, task_scans[0], "fmriprep", suffix)
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(derivative_path(self.config,self.scans[0],"fmriprep",suffix),dest)
        task_metadata = derivative_path(task_config,task_scans[0],"fmriprep",
                                        "space-MNI152NLin2009cAsym_desc-preproc_bold.json")
        task_metadata.write_text('{"SliceTimingCorrected":true}',encoding="utf-8")
        task_config_path = self.root / "task_config.json"
        task_config_path.write_text(json.dumps(task_config),encoding="utf-8")
        task_arguments = [BASH,wrapper.as_posix(),(REPO/"scripts/neuroimaging/run_fmriprep_task.sbatch").as_posix(),
                          "THU","sub-THU0001",task_config_path.as_posix(),self.root.as_posix()]
        preview = subprocess.run([*task_arguments,"--dry-run"],env=environment,text=True,capture_output=True,check=True)
        task_command = shlex.split(preview.stdout.strip())
        self.assertNotIn("--ignore",task_command)
        self.assertNotIn("--task-id",task_command)
        self.assertEqual(task_command[task_command.index("--bids-filter-file")+1],"/bids_filter.json")
        execution = subprocess.run(task_arguments,env=environment,text=True,capture_output=True)
        self.assertEqual(execution.returncode,0,execution.stderr)
        self.assertEqual(assert_completed(task_config,"fmriprep","sub-THU0001",task_scans)["command"],task_command)
        task_metadata.write_text('{"SliceTimingCorrected":false}',encoding="utf-8")
        with self.assertRaisesRegex(AssertionError,"STC was not performed"):
            finish_container(task_config,"fmriprep","sub-THU0001",task_scans,task_command,"mock-container")

        # A failed rerun must invalidate the old completion and release its lock.
        (fake_bin / "singularity").write_text(
            '#!/usr/bin/env bash\nif [[ "${@: -1}" == --version ]]; then printf "mock-container\\n"; else exit 7; fi\n',
            encoding="utf-8",
        )
        arguments[2] = (REPO / "scripts/neuroimaging/run_fmriprep.sbatch").as_posix()
        failed = subprocess.run(arguments, env=environment, text=True, capture_output=True)
        self.assertEqual(failed.returncode, 7, failed.stderr)
        self.assertFalse(record_path(self.config, "fmriprep", "sub-THU0001").exists())
        self.assertFalse((module_path(self.config, "fmriprep", "logs") / "locks/sub-THU0001.lock").exists())

    def test_qc_is_invalidated_by_a_new_head_motion_run(self):
        self.motion_qc()
        records = {subject: {"completed_at_utc": "first"} for subject in ("sub-THU0001", "sub-THU0002")}
        root = module_path(self.config, "head_motion", "logs")
        root.mkdir(parents=True, exist_ok=True)
        (root / "qc_provenance.json").write_text(json.dumps(dict(
            settings=self.config["head_motion"], head_motion_completed_at={subject: "first" for subject in records},
        )), encoding="utf-8")
        with patch("imaging.pipeline.assert_completed", side_effect=lambda config, stage, subject, scans: records[subject]):
            assert_qc_current(self.config, self.scans)
            records["sub-THU0002"]["completed_at_utc"] = "new-head-motion"
            with self.assertRaisesRegex(AssertionError, "rerun dataset-wide qc"):
                assert_qc_current(self.config, self.scans)

    def test_thresholds_are_fitted_per_dataset(self):
        self.motion_qc()
        thu = read_csv(module_path(self.config, "head_motion", "tables") / "qc_thresholds.csv")[0]
        xy = json.loads(json.dumps(self.config))
        xy["dataset"] = "XY"
        scans = []
        for subject in ("sub-THU0001", "sub-THU0002"):
            rows = read_csv(module_path(self.config, "head_motion", "tables") / f"subjects/{subject}.csv")
            for row in rows:
                row["dataset"] = "XY"
                row["mean_fd_mm"] = 0.2
                scans.append(row)
            from imaging.rest import write_csv
            write_csv(module_path(xy, "head_motion", "tables") / f"subjects/{subject}.csv", rows)
        summarize_qc(xy, scans)
        result = read_csv(module_path(xy, "head_motion", "tables") / "qc_thresholds.csv")[0]
        self.assertAlmostEqual(float(thu["fd_cutoff_mm"]), 0.1)
        self.assertAlmostEqual(float(result["fd_cutoff_mm"]), 0.2)


if __name__ == "__main__":
    unittest.main()
