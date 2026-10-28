"""Test the real filtered-design gate inside the XCP-D container (Nilearn required)."""

import importlib.util
import json
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import nibabel as nib
import numpy as np


REPO = Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec("nilearn"), "Run inside the XCP-D image")
class ResidualGate(unittest.TestCase):
    def verify(self, retained_task_signal):
        from nilearn.signal import butterworth, standardize_signal

        with tempfile.TemporaryDirectory(prefix="efny_residual_gate_") as folder:
            root = Path(folder)
            output = root / "xcpd"
            func = output / "sub-test/func"
            func.mkdir(parents=True)
            registry = root / "run.json"
            config = root / "config.json"
            config.write_text(json.dumps(dict(xcpd=dict(dummy_scans=0, upper_bpf_hz=0.1,
                lower_bpf_hz=0.01, bpf_order=2), atlases={"synthetic": 3})))
            registry.write_text(json.dumps(dict(config=str(config), tasks={"nback": dict(
                output_dir=str(output), pilots=["sub-test"])})))
            rng = np.random.default_rng(19)
            values = rng.normal(size=(100, 39))
            names = [f"nuisance_{i}" for i in range(36)] + ["task_0back", "task_2back", "task_cue"]
            np.savetxt(func / "sub-test_task-nback_design.tsv", values, delimiter="\t",
                       header="\t".join(names), comments="")
            filtered = butterworth(standardize_signal(values, detrend=True, standardize=False),
                sampling_rate=0.5, low_pass=0.1, high_pass=0.01, order=2, padtype="constant", padlen=99)
            signals = rng.normal(size=(100, 3))
            residual = signals - filtered @ np.linalg.lstsq(filtered, signals, rcond=None)[0]
            if retained_task_signal:
                residual += filtered[:, -1, None] * 5
            parcels = nib.cifti2.ParcelsAxis(["a", "b", "c"], [np.empty((0, 3), int)] * 3, [{}, {}, {}])
            image = nib.Cifti2Image(residual.astype(np.float32), header=nib.Cifti2Header.from_axes(
                (nib.cifti2.SeriesAxis(0, 2, 100), parcels)))
            nib.save(image, func / "sub-test_task-nback_space-fsLR_atlas-synthetic_den-91k_stat-mean_timeseries.ptseries.nii")
            with patch("sys.argv", ["audit_task_pilot_residuals.py", str(registry)]):
                if retained_task_signal:
                    with self.assertRaisesRegex(AssertionError, "Residual joint-design projection"):
                        runpy.run_path(str(REPO / "scripts/neuroimaging/audit_task_pilot_residuals.py"))
                else:
                    runpy.run_path(str(REPO / "scripts/neuroimaging/audit_task_pilot_residuals.py"))
                    rows = json.loads((root / "run_pilot_residual_audit.json").read_text())
                    self.assertLess(rows[0]["max_normalized_joint_projection"], 1e-5)

    def test_removed_task_signal_passes(self):
        self.verify(False)

    def test_retained_task_signal_fails(self):
        self.verify(True)


if __name__ == "__main__":
    unittest.main()
