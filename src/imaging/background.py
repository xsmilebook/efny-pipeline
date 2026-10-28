"""Audit task designs and export per-run background FC without rest-specific QC."""

import csv
import json
from pathlib import Path

import nibabel as nib
import numpy as np
from nibabel.cifti2 import SeriesAxis

from imaging.config import module_path
from imaging.rest import derivative_path, load_ptseries, write_csv


TASK_COLUMNS = {
    "nback": {"task_0back", "task_2back", "task_cue"},
    "sst": {"task_go_correct", "task_go_error", "task_stop_fail", "task_stop_success", "task_cue"},
    "switch": {"task_cue", "task_nonswitch1", "task_nonswitch2", "task_switch"},
}


def regression_config(config: dict) -> dict:
    """Read the JSON-formatted YAML and require the intended 36P plus task model."""
    path = Path(config["project_root"]) / config["task_xcpd"]["confounds_config"]
    model = json.loads(path.read_text(encoding="utf-8"))
    groups = model["confounds"]
    bases = ("trans_x", "trans_y", "trans_z", "rot_x", "rot_y", "rot_z", "global_signal", "csf", "white_matter")
    expected = {base + suffix for base in bases for suffix in ("", "_derivative1", "_power2", "_derivative1_power2")}
    columns = groups["preproc_confounds"]["columns"]
    assert len(columns) == 36 and set(columns) == expected, "Background model must retain all 36P columns"
    assert set(groups) == {"preproc_confounds", "task_confounds"}
    assert groups["preproc_confounds"]["dataset"] == "preprocessed"
    assert groups["task_confounds"]["dataset"] == "custom"
    assert groups["task_confounds"]["columns"] == ["^task_.*$"], "Task effects must be nuisance regressors"
    for group in groups.values():
        assert group["query"] == dict(space=None, cohort=None, res=None, den=None,
                                      desc="confounds", extension=".tsv", suffix="timeseries")
    return model


def inspect_confounds(config: dict, scan: dict) -> dict:
    """Audit one task design against its BOLD identity, STC sampling time and volume axis.

    Expected missing files and scientific mismatches are explicit audit statuses;
    malformed input formats raise. No input values or timestamps are corrected.
    """
    custom = Path(config["task_xcpd"]["confounds_dir"]) / scan["subject"] / scan["func_dir"] / (
        scan["scan_id"] + "_desc-confounds_timeseries.tsv")
    result = dict(scan_id=scan["scan_id"], subject=scan["subject"], task=scan["task"], run=scan["run"],
                  confounds=str(custom), ready=False, issues=[])
    missing = [str(p) for p in (custom, custom.with_suffix(".json")) if not p.is_file()]
    if missing:
        result["issues"] = ["missing custom confounds: " + ";".join(missing)]
        return result
    metadata = json.loads(custom.with_suffix(".json").read_text(encoding="utf-8"))
    provenance = metadata["TaskDesignProvenance"]
    with custom.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, delimiter="\t")
        columns = next(reader)
        values = np.asarray([[float(value) for value in row] for row in reader])
    issues = result["issues"]
    if not columns or len(set(columns)) != len(columns) or not set(columns) <= TASK_COLUMNS[scan["task"]]:
        issues.append("unexpected or duplicate task columns")
    assert values.ndim == 2 and values.shape[1] == len(columns), f"Task design orientation: {custom}"
    if not np.isfinite(values).all():
        issues.append("non-finite task regressors")
    source = nib.load(scan["source_bold"])
    frames = source.shape[3]
    source_json = json.loads(Path(scan["source_bold"]).with_name(scan["scan_id"] + "_bold.json").read_text(encoding="utf-8"))
    bold_metadata = json.loads(derivative_path(config, scan, "fmriprep",
        "space-MNI152NLin2009cAsym_desc-preproc_bold.json").read_text(encoding="utf-8"))
    image = nib.load(derivative_path(config, scan, "fmriprep", "space-fsLR_den-91k_bold.dtseries.nii"))
    axis = image.header.get_axis(0)
    assert isinstance(axis, SeriesAxis), f"Expected CIFTI time x grayordinate orientation: {scan['scan_id']}"
    tr = bold_metadata["RepetitionTime"]
    offset = bold_metadata["StartTime"]
    if str(Path(provenance["SourceBOLD"])) != str(Path(scan["source_bold"])):
        issues.append("custom design SourceBOLD differs from selected scan")
    if not (len(values) == provenance["NFrames"] == frames == axis.size):
        issues.append("BOLD/custom/CIFTI frame count mismatch")
    if not (axis.unit == "SECOND" and np.isclose(axis.step, tr, atol=1e-6, rtol=0)
            and np.isclose(provenance["RepetitionTime"], tr, atol=1e-6, rtol=0)
            and np.isclose(source_json["RepetitionTime"], tr, atol=1e-6, rtol=0)):
        issues.append("BOLD/custom/CIFTI TR mismatch")
    if bold_metadata["SliceTimingCorrected"] is not True:
        issues.append("STC was not performed")
    if not np.isclose(provenance["FrameTimeOffsetSeconds"], offset, atol=1e-6, rtol=0):
        issues.append("task frame offset differs from STC BOLD StartTime")
    if provenance["DummyVolumesRemovedHere"] != 0:
        issues.append("custom confounds have already removed dummy volumes")
    # Conditions absent from a run may legitimately have no column (e.g. no go errors).
    # Do not create zero columns or require the union of every task's conditions.
    constant = [name for name, vector in zip(columns, values.T) if np.ptp(vector) == 0]
    if constant:
        issues.append("constant task regressors: " + ";".join(constant))
    rank = int(np.linalg.matrix_rank(values)) if np.isfinite(values).all() else None
    if rank is not None and (rank == 0 or len(values) - rank - 36 - 2 < 1):
        issues.append("insufficient frames for task effects, 36P and detrending")
    preproc = derivative_path(config, scan, "fmriprep", "desc-confounds_timeseries.tsv")
    with preproc.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        preproc_columns = reader.fieldnames
        preproc_rows = list(reader)
    if len(preproc_rows) != frames:
        issues.append("BOLD/fMRIPrep confounds frame count mismatch")
    nuisance = regression_config(config)["confounds"]["preproc_confounds"]["columns"]
    if not set(nuisance) <= set(preproc_columns):
        issues.append("fMRIPrep confounds lack 36P columns")
    else:
        for name in nuisance:
            numeric = np.array([np.nan if row[name] in ("n/a", "NaN", "nan", "") else float(row[name])
                                for row in preproc_rows])
            # Only the first derivative-based value is undefined by construction in fMRIPrep.
            invalid = ~np.isfinite(numeric)
            if "_derivative1" in name and len(numeric) and np.isnan(numeric[0]):
                invalid[0] = False
            if invalid.any():
                issues.append("non-finite 36P values: " + name)
    result.update(columns=columns, frames=len(values), tr_seconds=tr,
                  frame_offset_seconds=provenance["FrameTimeOffsetSeconds"], bold_start_time_seconds=offset,
                  task_rank=rank, metadata=metadata,
                  tsv_size=custom.stat().st_size, tsv_mtime_ns=custom.stat().st_mtime_ns,
                  preproc_confounds=str(preproc), preproc_size=preproc.stat().st_size,
                  preproc_mtime_ns=preproc.stat().st_mtime_ns,
                  ready=not issues)
    return result


def prepare_background(config: dict, upstream: list[dict], subjects_file: Path | None) -> None:
    """Save a separate task inventory, exact run filters and explicit readiness audit."""
    subjects = None if subjects_file is None else subjects_file.read_text(encoding="utf-8-sig").splitlines()
    if subjects is not None:
        subjects = [s.strip() for s in subjects if s.strip()]
        assert subjects and len(subjects) == len(set(subjects)), "Empty or duplicated subject list"
    scans = [s for s in upstream if s["task"] == config["task"] and (subjects is None or s["subject"] in subjects)]
    assert scans, "No selected task scans in fMRIPrep inventory"
    if subjects is not None:
        assert set(subjects) == {s["subject"] for s in scans}, "Selected subject has no scan for this task"
    audit = [inspect_confounds(config, scan) for scan in scans]
    logs = module_path(config, "xcpd", "logs")
    write_csv(logs / "input_scans.csv", scans)
    (logs / "confounds_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    summary = []
    filters = logs / "filters"
    filters.mkdir(exist_ok=True)
    for subject in sorted({s["subject"] for s in scans}):
        selected = [s for s in scans if s["subject"] == subject]
        rows = [r for r in audit if r["subject"] == subject]
        summary.append(dict(dataset=config["dataset"], subject=subject, task=config["task"], runs=len(rows),
                            ready_runs=sum(r["ready"] for r in rows), ready=all(r["ready"] for r in rows),
                            reason=";".join(r["scan_id"] + ": " + ";".join(r["issues"]) for r in rows if r["issues"])))
        runs = [int(s["run"]) for s in selected if s["run"]]
        assert not runs or len(runs) == len(selected), "Cannot mix absent and numbered runs within one task"
        query = {"bold": {"task": config["task"], "run": runs or None}}
        (filters / f"{subject}.json").write_text(json.dumps(query, indent=2) + "\n", encoding="utf-8")
    write_csv(module_path(config, "xcpd", "tables") / "input_readiness.csv", summary)
    for label, ready in (("ready", True), ("blocked", False)):
        (logs / f"subjects_{label}.txt").write_text("".join(r["subject"] + "\n" for r in summary if r["ready"] == ready),
                                                  encoding="utf-8", newline="\n")
    print(f"{config['task']}: {sum(r['ready'] for r in audit)}/{len(audit)} runs ready; audit={logs / 'confounds_audit.json'}")


def validate_background_inputs(config: dict, scans: list[dict]) -> list[dict]:
    """Reject scientific mismatches and designs changed since the explicit prepare step."""
    current = [inspect_confounds(config, scan) for scan in scans]
    blocked = [r["scan_id"] + ": " + ";".join(r["issues"]) for r in current if not r["ready"]]
    assert not blocked, "Task confounds not ready: " + " | ".join(blocked)
    prepared = json.loads((module_path(config, "xcpd", "logs") / "confounds_audit.json").read_text(encoding="utf-8"))
    expected = {r["scan_id"]: r for r in prepared}
    assert all(row == expected[row["scan_id"]] for row in current), "Task confounds changed; prepare again"
    return current


def validate_joint_design(config: dict, scans: list[dict]) -> None:
    """Require XCP-D's saved design to contain the actual task columns and all 36P terms."""
    model = regression_config(config)
    nuisance = model["confounds"]["preproc_confounds"]["columns"]
    motion = ("trans_", "rot_")
    expected_nuisance = {c + "_filtered" if config["xcpd"]["motion_filter_type"] != "none" and c.startswith(motion) else c
                         for c in nuisance}
    rows = []
    for scan in scans:
        inputs = inspect_confounds(config, scan)
        design = derivative_path(config, scan, "xcpd", "design.tsv")
        with design.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, delimiter="\t")
            names = next(reader)
            values = np.asarray([[float(x) for x in row] for row in reader])
        assert len(names) == len(set(names)) and set(names) == expected_nuisance | set(inputs["columns"]), (
            f"XCP-D joint design columns differ: {scan['scan_id']}")
        assert values.shape == (inputs["frames"] - config["xcpd"]["dummy_scans"], len(names))
        assert np.isfinite(values).all(), f"Non-finite XCP-D design: {design}"
        # The saved design precedes BOLD bandpass filtering; task terms must be unchanged.
        with Path(inputs["confounds"]).open(encoding="utf-8-sig", newline="") as stream:
            original = list(csv.DictReader(stream, delimiter="\t"))
        for name in inputs["columns"]:
            original_column = np.array([float(row[name]) for row in original])
            assert np.allclose(values[:, names.index(name)], original_column[config["xcpd"]["dummy_scans"]:], atol=1e-6, rtol=1e-6), (
                f"Task regressor values changed in XCP-D design: {scan['scan_id']} {name}")
        rank = int(np.linalg.matrix_rank(np.column_stack([np.ones(len(values)), np.arange(len(values)), values])))
        assert rank < len(values), f"Saturated XCP-D design: {scan['scan_id']}"
        rows.append(dict(scan_id=scan["scan_id"], columns=names, frames=len(values), design_rank=rank,
                         nominal_residual_dof=len(values) - rank))
    path = module_path(config, "xcpd", "logs") / "design_audit" / f"{scans[0]['subject']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


def compute_background_fc(config: dict, scans: list[dict], subject: str) -> None:
    """Compute Pearson r and Fisher z for each residual run independently, retaining parcel labels."""
    rows, sources = [], []
    for scan in (s for s in scans if s["subject"] == subject):
        summary = dict(dataset=config["dataset"], subject=subject, task=scan["task"], run=scan["run"], scan_id=scan["scan_id"])
        for atlas, parcels in config["atlases"].items():
            path = derivative_path(config, scan, "xcpd", f"space-fsLR_atlas-{atlas}_den-91k_stat-mean_timeseries.ptseries.nii")
            values, labels, step = load_ptseries(path, parcels)
            correlation = np.corrcoef(values, rowvar=False)
            assert np.isfinite(correlation).all(), f"Undefined background FC: {scan['scan_id']} {atlas}"
            fisher_z = np.arctanh(np.clip(correlation, -0.999999, 0.999999))
            np.fill_diagonal(correlation, 1)
            np.fill_diagonal(fisher_z, 0)
            output = module_path(config, "background_fc", "processed") / subject / scan["scan_id"] / atlas
            for kind, matrix, suffix in (("raw", correlation, "fc"), ("fisher_z", fisher_z, "fc_fisher_z")):
                dest = output / kind / f"{scan['scan_id']}_atlas-{atlas}_{suffix}.csv"
                dest.parent.mkdir(parents=True, exist_ok=True)
                with dest.open("w", newline="", encoding="utf-8") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(["parcel", *labels])
                    writer.writerows([label, *vector] for label, vector in zip(labels, matrix))
            summary.update(frames=len(values), tr_seconds=step)
            summary[f"{atlas}_parcels"] = parcels
            sources.append(dict(scan_id=scan["scan_id"], atlas=atlas, ptseries=str(path), labels=labels))
        rows.append(summary)
    write_csv(module_path(config, "background_fc", "tables") / "subjects" / f"{subject}.csv", rows)
    dest = module_path(config, "background_fc", "logs") / "sources" / f"{subject}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(sources, indent=2) + "\n", encoding="utf-8")


def validate_background_fc(config: dict, scans: list[dict]) -> None:
    """Check saved matrix labels, symmetry and r/z correspondence against each residual run."""
    for scan in scans:
        for atlas, parcels in config["atlases"].items():
            source = derivative_path(config, scan, "xcpd", f"space-fsLR_atlas-{atlas}_den-91k_stat-mean_timeseries.ptseries.nii")
            values, labels, _ = load_ptseries(source, parcels)
            expected_r = np.corrcoef(values, rowvar=False)
            expected_z = np.arctanh(np.clip(expected_r, -0.999999, 0.999999))
            np.fill_diagonal(expected_r, 1)
            np.fill_diagonal(expected_z, 0)
            root = module_path(config, "background_fc", "processed") / scan["subject"] / scan["scan_id"] / atlas
            for kind, suffix, expected in (("raw", "fc", expected_r), ("fisher_z", "fc_fisher_z", expected_z)):
                path = root / kind / f"{scan['scan_id']}_atlas-{atlas}_{suffix}.csv"
                with path.open(encoding="utf-8", newline="") as stream:
                    reader = csv.reader(stream)
                    assert next(reader) == ["parcel", *labels], f"FC parcel column order: {path}"
                    rows = list(reader)
                assert [r[0] for r in rows] == labels, f"FC parcel row order: {path}"
                matrix = np.array([[float(x) for x in r[1:]] for r in rows])
                assert matrix.shape == (parcels, parcels) and np.isfinite(matrix).all()
                assert np.allclose(matrix, expected, atol=1e-10, rtol=1e-10), f"FC differs from residual run: {path}"
