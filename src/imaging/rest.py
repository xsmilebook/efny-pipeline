"""Rest FD quality control and subject-level CIFTI connectivity."""

import csv
from collections import defaultdict
from pathlib import Path
from statistics import quantiles

import nibabel as nib
import numpy as np
from nibabel.cifti2 import ParcelsAxis, SeriesAxis

from imaging.config import module_path


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def derivative_path(config: dict, scan: dict, stage: str, suffix: str) -> Path:
    return module_path(config, stage, "interim") / scan["subject"] / scan["func_dir"] / (
        scan["scan_id"] + "_" + suffix
    )


def load_ptseries(path: Path, parcels: int) -> tuple[np.ndarray, list[str], float]:
    """Return frames x parcels, ordered labels and TR (seconds) from explicit CIFTI axes."""
    image = nib.load(path, mmap=False)
    axes = [image.header.get_axis(i) for i in range(2)]
    time_axis = next(i for i, axis in enumerate(axes) if isinstance(axis, SeriesAxis))
    parcel_axis = next(i for i, axis in enumerate(axes) if isinstance(axis, ParcelsAxis))
    data = np.moveaxis(image.get_fdata(dtype=np.float64), time_axis, 0)
    labels = [str(name) for name in axes[parcel_axis].name]
    assert len(labels) == parcels and len(set(labels)) == parcels, f"Atlas labels: {path}"
    assert data.shape[1] == parcels, f"Atlas size: {path}"
    assert axes[time_axis].unit == "SECOND" and axes[time_axis].step > 0, f"Invalid CIFTI TR: {path}"
    assert np.isfinite(data).all(), f"Non-finite parcel signals: {path}"
    assert data.shape[0] >= 2 and np.all(np.std(data, axis=0) > 0), f"Constant parcel: {path}"
    return data, labels, axes[time_axis].step


def compute_motion(config: dict, scans: list[dict], subject: str) -> None:
    """Summarize original fMRIPrep FD (mm) over the same volume window as XCP-D."""
    threshold = config["head_motion"]["fd_threshold_mm"]
    dummy = config["xcpd"]["dummy_scans"]
    rows = []
    for scan in scans:
        if scan["subject"] != subject:
            continue
        confounds = derivative_path(config, scan, "fmriprep", "desc-confounds_timeseries.tsv")
        with confounds.open(encoding="utf-8-sig", newline="") as stream:
            records = list(csv.DictReader(stream, delimiter="\t"))
        source = nib.load(scan["source_bold"])
        assert len(source.shape) == 4 and source.shape[3] == len(records), (
            f"BOLD/confounds volume mismatch: {scan['scan_id']}"
        )
        fd_values = []
        missing_first = 0
        for index, record in enumerate(records):
            value = record["framewise_displacement"]
            # The first derivative-based FD is undefined; no other missing FD is accepted.
            if index == 0 and value in ("n/a", "NaN", "nan", ""):
                missing_first = int(dummy == 0)
                continue
            fd = float(value)
            assert np.isfinite(fd) and fd >= 0, f"Invalid FD at volume {index}: {confounds}"
            if index >= dummy:
                fd_values.append(fd)
        frames = len(records) - dummy
        assert frames >= 2 and len(fd_values) + missing_first == frames
        row = dict(scan)
        row.update(
            frames=frames,
            fd_valid_frames=len(fd_values),
            fd_missing_first=missing_first,
            mean_fd_mm=float(np.mean(fd_values)),
            high_motion_ratio=sum(fd > threshold for fd in fd_values) / frames,
            fd_threshold_mm=threshold,
            dummy_scans=dummy,
            confounds=str(confounds),
        )
        rows.append(row)
    assert rows, f"No rest scans for {subject}"
    write_csv(module_path(config, "head_motion", "tables") / "subjects" / f"{subject}.csv", rows)


def summarize_qc(config: dict, scans: list[dict]) -> None:
    """Apply dataset-specific Q3+1.5 IQR and FD>0.3 mm ratio QC to each rest run."""
    rows = []
    subjects = sorted({scan["subject"] for scan in scans})
    for subject in subjects:
        rows.extend(read_csv(module_path(config, "head_motion", "tables") / "subjects" / f"{subject}.csv"))
    expected = {(row["subject"], row["scan_id"]) for row in scans}
    observed = [(row["subject"], row["scan_id"]) for row in rows]
    assert len(observed) == len(set(observed)) and set(observed) == expected, "QC scan identities differ"
    settings = config["head_motion"]
    for row in rows:
        assert row["dataset"] == config["dataset"]
        assert float(row["fd_threshold_mm"]) == settings["fd_threshold_mm"]
        assert int(row["dummy_scans"]) == config["xcpd"]["dummy_scans"]
    values = [float(row["mean_fd_mm"]) for row in rows]
    assert len(values) >= 4 and np.isfinite(values).all(), "IQR QC requires at least four finite run means"
    q1, _, q3 = quantiles(values, n=4, method="inclusive")
    cutoff = q3 + settings["fd_outlier_scale"] * (q3 - q1)
    groups = defaultdict(list)
    for row in rows:
        valid = float(row["mean_fd_mm"]) <= cutoff and (
            float(row["high_motion_ratio"]) <= settings["high_motion_ratio_threshold"]
        )
        row.update(fd_cutoff_mm=cutoff, run_valid=str(valid).lower())
        groups[row["subject"]].append(row)
    subject_rows = []
    for subject, run_rows in sorted(groups.items()):
        valid_runs = sum(row["run_valid"] == "true" for row in run_rows)
        subject_rows.append(dict(
            dataset=config["dataset"], subject=subject,
            total_runs=len(run_rows), valid_runs=valid_runs,
            min_valid_runs=settings["min_valid_runs"],
            subject_valid=str(valid_runs >= settings["min_valid_runs"]).lower(),
        ))
    output = module_path(config, "head_motion", "tables")
    write_csv(output / "run_qc.csv", rows)
    write_csv(output / "subject_qc.csv", subject_rows)
    write_csv(output / "qc_thresholds.csv", [dict(
        dataset=config["dataset"], run_count=len(rows), q1_mm=q1, q3_mm=q3,
        iqr_mm=q3 - q1, fd_cutoff_mm=cutoff,
        **settings,
    )])
    print(f"{config['dataset']}: FD cutoff={cutoff:.6f} mm; wrote {len(subject_rows)} subject QC rows")


def compute_fc(config: dict, scans: list[dict], subject: str) -> None:
    """Concatenate a subject's QC-valid runs, then Pearson r and Fisher z; never impute."""
    qc_dir = module_path(config, "head_motion", "tables")
    subjects = [row for row in read_csv(qc_dir / "subject_qc.csv") if row["subject"] == subject]
    assert len(subjects) == 1 and subjects[0]["subject_valid"] == "true", f"Subject failed QC: {subject}"
    rows = [row for row in read_csv(qc_dir / "run_qc.csv") if row["subject"] == subject]
    source_scans = {scan["scan_id"]: scan for scan in scans if scan["subject"] == subject}
    assert {row["scan_id"] for row in rows} == set(source_scans), "FC/QC scan identities differ"
    provenance = []
    valid = [row for row in rows if row["run_valid"] == "true"]
    valid.sort(key=lambda row: (int(row["run"]), row["scan_id"]))
    assert len(valid) >= config["head_motion"]["min_valid_runs"]
    sample = subject
    for atlas, parcels in config["atlases"].items():
        arrays, labels, steps, sources = [], [], [], []
        for row in valid:
            assert int(row["dummy_scans"]) == config["xcpd"]["dummy_scans"]
            assert float(row["fd_threshold_mm"]) == config["head_motion"]["fd_threshold_mm"]
            scan = source_scans[row["scan_id"]]
            path = derivative_path(config, scan, "xcpd", f"space-fsLR_atlas-{atlas}_den-91k_stat-mean_timeseries.ptseries.nii")
            array, names, step = load_ptseries(path, parcels)
            assert array.shape[0] == int(row["frames"]), f"XCP-D/QC time window mismatch: {path}"
            if labels:
                assert names == labels, f"Parcel order differs across runs: {sample} {atlas}"
                assert np.isclose(step, steps[0]), f"TR differs across runs: {sample}"
            labels = names
            arrays.append(array)
            steps.append(step)
            sources.append(str(path))
        # Preserve run means and amplitudes, matching the reference concatenation rule.
        timeseries = np.concatenate(arrays, axis=0)
        correlation = np.corrcoef(timeseries, rowvar=False)
        assert np.isfinite(correlation).all(), f"Undefined FC: {sample} {atlas}"
        fisher_z = np.arctanh(np.clip(correlation, -0.999999, 0.999999))
        np.fill_diagonal(correlation, 1.0)
        np.fill_diagonal(fisher_z, 0.0)
        output = module_path(config, "rest_fc", "processed") / subject
        for kind, matrix, suffix in [("raw", correlation, "fc"), ("fisher_z", fisher_z, "fc_fisher_z")]:
            path = output / atlas / kind / f"{sample}_atlas-{atlas}_{suffix}.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(["parcel", *labels])
                writer.writerows([label, *values] for label, values in zip(labels, matrix))
        provenance.append(dict(
            dataset=config["dataset"], subject=subject, atlas=atlas,
            parcels=parcels, frames=timeseries.shape[0], tr_seconds=steps[0],
            scan_ids=";".join(row["scan_id"] for row in valid), ptseries=";".join(sources),
        ))
    write_csv(module_path(config, "rest_fc", "tables") / "subjects" / f"{subject}.csv", provenance)
