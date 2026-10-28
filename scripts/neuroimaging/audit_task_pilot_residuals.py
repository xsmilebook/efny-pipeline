"""Check pilot residual projection against the actual detrended, bandpassed joint design.

Run inside the configured XCP-D image, which supplies its installed Nilearn version.
The input design.tsv precedes filtering. With dummy=0 and FD censoring disabled,
XCP-D applies this same temporal transformation to BOLD and nuisance columns.
Spatial parcel averaging preserves their regression orthogonality.
"""

import csv
import json
import sys
from pathlib import Path

import nibabel as nib
import numpy as np
from nilearn.signal import butterworth, standardize_signal


registry = Path(sys.argv[1])
record = json.loads(registry.read_text())
config = json.loads(Path(record["config"]).read_text())
settings = config["xcpd"]
assert settings["dummy_scans"] == 0
rows = []
for task, item in record["tasks"].items():
    output = Path(item["output_dir"])
    for subject in item["pilots"]:
        for design in sorted((output / subject / "func").glob(f"*_task-{task}*_design.tsv")):
            scan_id = design.name.removesuffix("_design.tsv")
            with design.open() as stream:
                reader = csv.reader(stream, delimiter="\t")
                names = next(reader)
                values = np.array([[float(value) for value in row] for row in reader])
            task_columns = np.array([name.startswith("task_") for name in names])
            assert task_columns.any(), f"Task terms absent: {design}"
            for atlas in config["atlases"]:
                path = design.with_name(scan_id + f"_space-fsLR_atlas-{atlas}_den-91k_stat-mean_timeseries.ptseries.nii")
                image = nib.load(path)
                axis = image.header.get_axis(0)
                residuals = image.get_fdata()
                assert residuals.shape[0] == len(values)
                filtered = standardize_signal(values.copy(), detrend=True, standardize=False)
                filtered = butterworth(filtered, sampling_rate=1 / axis.step,
                                       low_pass=settings["upper_bpf_hz"], high_pass=settings["lower_bpf_hz"],
                                       order=settings["bpf_order"], padtype="constant", padlen=len(values) - 1)
                norms = np.linalg.norm(filtered, axis=0)
                assert np.all(norms[task_columns] > 0), f"Filtered task term vanished: {design}"
                nonzero = norms > 0
                projection = np.abs(filtered[:, nonzero].T @ residuals) / (
                    norms[nonzero, None] * np.linalg.norm(residuals, axis=0)[None, :])
                assert np.isfinite(projection).all()
                maximum = float(projection.max())
                # Allow float32 CIFTI serialization error, not meaningful residual task projection.
                assert maximum < 1e-5, f"Residual joint-design projection {maximum}: {path}"
                rows.append(dict(subject=subject, task=task, scan_id=scan_id, atlas=atlas,
                                 frames=len(values), filtered_design_rank=int(np.linalg.matrix_rank(filtered)),
                                 max_normalized_joint_projection=maximum,
                                 max_normalized_task_projection=float(projection[task_columns[nonzero]].max())))
    assert {row["subject"] for row in rows if row["task"] == task} == set(item["pilots"])
destination = registry.with_name(registry.stem + "_pilot_residual_audit.json")
destination.write_text(json.dumps(rows, indent=2) + "\n")
print(f"Pilot residual orthogonality passed: {len(rows)} run/atlas combinations; {destination}")
