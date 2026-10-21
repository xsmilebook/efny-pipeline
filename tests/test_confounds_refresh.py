"""Scientific checks for a motion-only replacement of aligned THU confounds."""

import csv
import json
import runpy
import shutil
import tempfile
import unittest
from pathlib import Path

import nibabel as nib
import numpy as np
from nibabel.cifti2 import BrainModelAxis, SeriesAxis

from imaging.rest import derivative_path


ROOT = Path(__file__).resolve().parents[1]
AUDIT_RUN = runpy.run_path(str(ROOT / "scripts/neuroimaging/refresh_thu_rest_confounds.py"))["audit_run"]


class ConfoundsRefreshTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "temp").mkdir(exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix="smoke_confounds_refresh_", dir=ROOT / "temp"))
        self.addCleanup(shutil.rmtree, self.root)
        self.config = dict(project_root=str(self.root), dataset="THU", scope="rest", fmriprep=dict(ignore=[]))
        self.scan = dict(subject="sub-THU1", func_dir="func", scan_id="sub-THU1_task-rest_run-1",
                         source_bold=str(self.root / "bold.nii.gz"))
        nib.save(nib.Nifti1Image(np.zeros((2, 2, 2, 5)), np.eye(4)), self.scan["source_bold"])
        cifti = derivative_path(self.config, self.scan, "fmriprep", "space-fsLR_den-91k_bold.dtseries.nii")
        cifti.parent.mkdir(parents=True)
        axes = (SeriesAxis(0, 2, 5), BrainModelAxis.from_mask(np.ones(2, dtype=bool), name="CortexLeft"))
        nib.save(nib.Cifti2Image(np.zeros((5, 2)), header=nib.Cifti2Header.from_axes(axes)), cifti)
        self.target = derivative_path(self.config, self.scan, "fmriprep", "desc-confounds_timeseries.tsv")
        self.source_root = self.root / "corrected"
        self.source = self.source_root / "sub-THU1" / "func" / self.target.name
        self.source.parent.mkdir(parents=True)
        motion = [f"{kind}_{axis}" for kind in ("rot", "trans") for axis in "xyz"]
        values = np.arange(30).reshape(5, 6) / 10000
        delta = np.diff(values, axis=0)
        data = {"global_signal": [str(x) for x in range(5)], "framewise_displacement": ["n/a", *map(str, np.abs(delta[:, 3:]).sum(axis=1) + 50 * np.abs(delta[:, :3]).sum(axis=1))]}
        data["std_dvars"] = ["n/a", "0", "0", "0", "0"]
        for index, name in enumerate(motion):
            data[name] = list(map(str, values[:, index]))
            data[name + "_derivative1"] = ["n/a", *map(str, delta[:, index])]
            data[name + "_power2"] = list(map(str, values[:, index] ** 2))
            data[name + "_derivative1_power2"] = ["n/a", *map(str, delta[:, index] ** 2)]
        self.columns = list(data)
        self.rows = [dict(zip(self.columns, row)) for row in zip(*data.values())]
        self.write(self.target)
        self.write(self.source)
        metadata = {name: dict(Units="rad" if name.startswith("rot") else "mm") for name in motion}
        metadata["framewise_displacement"] = dict(Units="mm")
        self.source.with_suffix(".json").write_text(json.dumps(metadata))

    def write(self, path):
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, self.columns, delimiter="\t")
            writer.writeheader()
            writer.writerows(self.rows)

    def test_valid_motion_replacement(self):
        self.rows[1]["framewise_displacement"] = "0.01"
        self.write(self.target)
        result = AUDIT_RUN(self.config, self.scan, self.source_root)
        self.assertEqual(result["changed_columns"], "framewise_displacement")
        self.assertEqual(result["frames"], 5)

    def test_reject_unrelated_signal_change(self):
        self.rows[2]["global_signal"] = "999"
        self.write(self.source)
        with self.assertRaisesRegex(AssertionError, "Non-motion confounds changed"):
            AUDIT_RUN(self.config, self.scan, self.source_root)

    def test_reject_inconsistent_fd(self):
        self.rows[2]["framewise_displacement"] = "0.001"
        self.write(self.source)
        with self.assertRaises(AssertionError):
            AUDIT_RUN(self.config, self.scan, self.source_root)

    def test_reject_volume_mismatch(self):
        self.rows.pop()
        self.write(self.source)
        with self.assertRaises(AssertionError):
            AUDIT_RUN(self.config, self.scan, self.source_root)

    def test_accept_added_motion_outlier_column(self):
        self.rows[2]["std_dvars"] = "2.0"
        self.write(self.target)
        self.columns.append("motion_outlier00")
        for index, row in enumerate(self.rows):
            row["motion_outlier00"] = str(int(index == 2))
        self.write(self.source)
        metadata = json.loads(self.source.with_suffix(".json").read_text())
        metadata["motion_outlier00"] = dict(Description="FD > 0.5 mm or standardized DVARS > 1.5.")
        self.source.with_suffix(".json").write_text(json.dumps(metadata))
        result = AUDIT_RUN(self.config, self.scan, self.source_root)
        self.assertEqual(result["corrected_motion_outliers"], 1)
        self.assertEqual(result["changed_columns"], "motion_outlier00")

    def test_reject_incorrect_motion_outlier_column(self):
        self.columns.append("motion_outlier00")
        for index, row in enumerate(self.rows):
            row["motion_outlier00"] = str(int(index == 2))
        self.write(self.source)
        with self.assertRaisesRegex(AssertionError, "Incorrect motion outlier flags"):
            AUDIT_RUN(self.config, self.scan, self.source_root)


if __name__ == "__main__":
    unittest.main()
