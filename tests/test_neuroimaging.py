"""Synthetic scientific checks; all temporary images stay under temp/smoke_* and are removed."""

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import nibabel as nib
import numpy as np
from nibabel.cifti2 import BrainModelAxis, ParcelsAxis, SeriesAxis

from imaging.config import load_config, module_path
from imaging.pipeline import (
    assert_completed, assert_qc_current, check, container_command, discover_scans, input_scans, prepare,
    record_path, run_stage, submit,
)
from imaging.rest import compute_fc, compute_motion, derivative_path, load_ptseries, read_csv, summarize_qc


REPO = Path(__file__).resolve().parents[1]


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
        self.assertIn("DATA_C/projects/efny-pipeline", config["project_root"])
        self.assertEqual(config["head_motion"]["min_valid_runs"], 2)
        with self.assertRaises(ValueError):
            load_config(REPO / "configs/neuroimaging.json", "XY")

    def test_numeric_run_order_and_reject_sessions(self):
        self.assertEqual([scan["run"] for scan in self.scans[:2]], ["1", "10"])
        (self.root / "bids/sub-THU0001/ses-01").mkdir()
        with self.assertRaisesRegex(AssertionError, "Session"):
            discover_scans(self.config, None)

    def test_missing_run_is_an_error(self):
        source = Path(self.scans[0]["source_bold"])
        source.rename(source.with_name(source.name.replace("_run-1", "")))
        with self.assertRaises(KeyError):
            discover_scans(self.config, None)

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
        with self.assertRaisesRegex(AssertionError, "failed QC"):
            compute_fc(self.config, self.scans, "sub-THU0001")

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

    def test_container_commands_and_submission_preview(self):
        fmriprep, _ = container_command(self.config, "fmriprep", "sub-THU0001", 6)
        self.assertIn(str(self.root / "bids") + ":/BIDS:ro", fmriprep)
        self.assertNotIn("--skip-bids-validation", fmriprep)
        xcpd, environment = container_command(self.config, "xcpd", "sub-THU0001", 1)
        self.assertEqual(xcpd[xcpd.index("--fd-thresh") + 1], "0")
        self.assertEqual(xcpd[xcpd.index("--dummy-scans") + 1], "0")
        self.assertEqual(xcpd[xcpd.index("--output-layout") + 1], "bids")
        self.assertFalse(any("proxy" in key.lower() for key in environment))
        output = io.StringIO()
        with redirect_stdout(output):
            submit(self.config, "fmriprep", REPO / "configs/neuroimaging.json", self.scans, None, True)
        self.assertEqual(output.getvalue().count("sbatch --parsable"), 2)
        self.assertIn("--cpus-per-task 6", output.getvalue())
        self.assertNotIn("--time", output.getvalue())
        self.assertNotIn("--mem", output.getvalue())

    def test_completion_tracks_reruns_and_missing_products(self):
        prepare(self.config, None)
        scans = input_scans(self.config)
        with patch("imaging.pipeline.subprocess.run"), patch("imaging.pipeline.subprocess.check_output", return_value="synthetic-version"):
            run_stage(self.config, "fmriprep", "sub-THU0001", scans, False)
            run_stage(self.config, "xcpd", "sub-THU0001", scans, False)
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
