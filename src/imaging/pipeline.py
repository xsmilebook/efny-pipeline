"""Explicit preprocessing, rest FC and task background FC submission and audits."""

import argparse
import csv
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from imaging.config import load_config, module_path, shell_config
from imaging.background import (
    compute_background_fc, prepare_background, regression_config,
    validate_background_inputs, validate_background_fc, validate_joint_design,
)
from imaging.rest import (
    compute_fc, compute_motion, derivative_path, load_ptseries, read_csv, summarize_qc,
    write_csv, write_motion_qc_tables,
)


STAGES = ("fmriprep", "xcpd", "head_motion", "rest_fc", "background_fc")
UPSTREAM = {"fmriprep": (), "xcpd": ("fmriprep",), "head_motion": ("xcpd",),
            "rest_fc": ("xcpd", "head_motion"), "background_fc": ("xcpd",)}


def discover_scans(config: dict, subjects_file: Path | None) -> list[dict]:
    """Inventory selected single-echo BOLD; task runs may legitimately omit the run entity."""
    bids = Path(config["bids_dir"])
    task_scope = config.get("scope", "rest") == "task"
    tasks = config["task_fmri"]["tasks"] if task_scope else ["rest"]
    prefix = config["datasets"][config["dataset"]]["subject_prefix"]
    subjects = (
        subjects_file.read_text(encoding="utf-8-sig").splitlines()
        if subjects_file else sorted(path.name for path in bids.glob(prefix + "*") if path.is_dir())
    )
    subjects = [subject.strip() for subject in subjects if subject.strip()]
    assert subjects and len(subjects) == len(set(subjects)), "Empty or duplicated subject list"
    scans = []
    for subject in subjects:
        assert re.fullmatch(r"sub-[A-Za-z0-9]+", subject) and subject.startswith(prefix), subject
        subject_dir = bids / subject
        assert not list(subject_dir.glob("ses-*")), f"Session directories are unsupported: {subject}"
        subject_scans = []
        for path in sorted((subject_dir / "func").glob(f"{subject}_task-*_bold.nii*")):
            stem = path.name.removesuffix(".gz").removesuffix(".nii")
            entities = dict(token.split("-", 1) for token in stem.split("_")[:-1])
            if entities["task"] not in tasks:
                continue
            assert "ses" not in entities and "echo" not in entities, f"Unsupported session/echo: {path}"
            run = entities.get("run", "") if task_scope else entities["run"]
            assert (task_scope and run == "") or (run.isdigit() and int(run) > 0), f"Expected numeric run: {path}"
            if "slicetiming" not in config["fmriprep"]["ignore"]:
                metadata = json.loads(path.with_name(stem + ".json").read_text(encoding="utf-8"))
                assert metadata.get("SliceTiming"), f"STC requires SliceTiming: {path}"
                tr = metadata["RepetitionTime"]
                assert tr > 0 and all(0 <= t < tr for t in metadata["SliceTiming"]), f"Invalid SliceTiming/TR: {path}"
            subject_scans.append(dict(
                dataset=config["dataset"], subject=subject, run=run,
                scan_id=stem.removesuffix("_bold"), func_dir="func", source_bold=str(path),
            ))
            if task_scope:
                subject_scans[-1]["task"] = entities["task"]
        assert subject_scans, f"No selected {tasks} BOLD scans: {subject}"
        if task_scope:
            identities = [(row["task"], int(row["run"]) if row["run"] else None) for row in subject_scans]
            assert len(set(identities)) == len(identities), f"Repeated task/run identities: {subject}"
            scans.extend(sorted(subject_scans, key=lambda row: (row["task"], int(row["run"]) if row["run"] else 0)))
        else:
            assert len({int(row["run"]) for row in subject_scans}) == len(subject_scans), f"Repeated rest run numbers: {subject}"
            scans.extend(sorted(subject_scans, key=lambda row: int(row["run"])))
    return scans


def prepare(config: dict, subjects_file: Path | None) -> None:
    """Save explicit source run identities and a reviewable dataset configuration."""
    scans = discover_scans(config, subjects_file)
    root = module_path(config, "fmriprep", "logs")
    write_csv(root / "input_scans.csv", scans)
    (root / "subjects.txt").write_text(
        "\n".join(dict.fromkeys(row["subject"] for row in scans)) + "\n", encoding="utf-8"
    )
    (root / "resolved_config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    if config.get("scope", "rest") == "task":
        (root / "bids_filter.json").write_text(
            json.dumps({"bold": {"task": config["task_fmri"]["tasks"]}}, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(scans)} {config.get('scope', 'rest')} runs for {len({row['subject'] for row in scans})} {config['dataset']} subjects")


def input_scans(config: dict) -> list[dict]:
    scans = read_csv(module_path(config, "fmriprep", "logs") / "input_scans.csv")
    assert scans and all(row["dataset"] == config["dataset"] for row in scans)
    expected_bids = Path(config["bids_dir"])
    assert all(Path(row["source_bold"]).is_relative_to(expected_bids) for row in scans), (
        "Input BIDS root changed; prepare the dataset again"
    )
    return scans


def background_scans(config: dict) -> list[dict]:
    """Read the selected task inventory without replacing the full fMRIPrep inventory."""
    scans = read_csv(module_path(config, "xcpd", "logs") / "input_scans.csv")
    upstream = {s["scan_id"]: s for s in input_scans(config)}
    assert scans and len({s["scan_id"] for s in scans}) == len(scans), "Empty or duplicate background scan identities"
    assert all(s["task"] == config["task"] and s == upstream[s["scan_id"]] for s in scans), (
        "Background inventory differs from selected task/fMRIPrep input; prepare again")
    return scans


def processing_settings(config: dict, stage: str) -> dict:
    """Describe scientific settings used to reject stale completion records."""
    keys = {
        "fmriprep": ("fmriprep",), "xcpd": ("xcpd", "atlases"),
        "head_motion": ("head_motion", "xcpd"), "rest_fc": ("head_motion", "xcpd", "atlases"),
        "background_fc": ("xcpd", "atlases"),
    }[stage]
    settings = {key: config[key] for key in keys}
    if stage == "fmriprep" and not config["fmriprep"]["ignore"]:
        # An empty ignore list is the original STC behavior, including older completion records.
        settings["fmriprep"] = {key: value for key, value in config["fmriprep"].items() if key != "ignore"}
    if config.get("scope", "rest") == "task":
        settings["task_fmri"] = config["task_fmri"]
        if stage != "fmriprep":
            settings.update(task=config["task"], task_xcpd=config["task_xcpd"],
                            background_regression=regression_config(config))
            settings["custom_dataset"] = json.loads((Path(config["task_xcpd"]["confounds_dir"]) /
                                                      "dataset_description.json").read_text(encoding="utf-8"))
    if stage in ("fmriprep", "xcpd"):
        settings["image"] = config["tools"][stage + "_image"]
    return settings


def record_path(config: dict, stage: str, subject: str) -> Path:
    return module_path(config, stage, "logs") / "completed" / f"{subject}.json"


def assert_completed(config: dict, stage: str, subject: str, scans: list[dict]) -> dict:
    """Reject outputs whose scientific settings, input identities or upstream run have changed."""
    if config.get("scope") == "task" and stage == "fmriprep":
        # Existing preprocessing markers contain ALL tasks for this subject.
        scans = input_scans(config)
    record = json.loads(record_path(config, stage, subject).read_text(encoding="utf-8"))
    assert record["processing"] == processing_settings(config, stage), f"Stale {stage} settings: {subject}"
    assert record["scans"] == [scan for scan in scans if scan["subject"] == subject], f"Stale {stage} inputs: {subject}"
    if config.get("scope") == "task" and stage == "xcpd":
        current = validate_background_inputs(config, [s for s in scans if s["subject"] == subject])
        assert record["task_confounds"] == current, f"Task confounds changed since XCP-D: {subject}"
    for previous in UPSTREAM[stage]:
        upstream = assert_completed(config, previous, subject, scans)
        assert record["upstream_completed_at"][previous] == upstream["completed_at_utc"], (
            f"{previous} was rerun; rerun {stage} for {subject}"
        )
    return record


def assert_qc_current(config: dict, scans: list[dict]) -> None:
    """Require a dataset-wide QC fit after the latest head-motion summaries and settings."""
    provenance = json.loads((module_path(config, "head_motion", "logs") / "qc_provenance.json").read_text(encoding="utf-8"))
    assert provenance["settings"] == config["head_motion"], "QC settings changed; rerun qc"
    subjects = sorted({scan["subject"] for scan in scans})
    current = {subject: assert_completed(config, "head_motion", subject, scans)["completed_at_utc"] for subject in subjects}
    assert provenance["head_motion_completed_at"] == current, "Head-motion inputs changed; rerun dataset-wide qc"


def save_record(config: dict, stage: str, subject: str, scans: list[dict], command: list[str], version: str) -> None:
    """Record successful execution, explicit run identities and tool provenance without hashes."""
    root = Path(config["project_root"])
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root, text=True).strip())
    record = dict(
        stage=stage, dataset=config["dataset"], subject=subject,
        completed_at_utc=datetime.now(timezone.utc).isoformat(), code_commit=commit, tracked_worktree_dirty=dirty,
        job_id=os.environ.get("SLURM_JOB_ID"), command=command, tool_version=version,
        processing=processing_settings(config, stage),
        scans=[scan for scan in scans if scan["subject"] == subject],
        resolved_config=config,
        upstream_completed_at={previous: assert_completed(config, previous, subject, scans)["completed_at_utc"]
                               for previous in UPSTREAM[stage]},
    )
    if config.get("scope") == "task" and stage == "xcpd":
        record["task_confounds"] = validate_background_inputs(config, [s for s in scans if s["subject"] == subject])
    path = record_path(config, stage, subject)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def required_products(config: dict, stage: str, scans: list[dict]) -> list[Path]:
    """List the products required for this exact source inventory, not old log messages."""
    if stage == "background_fc":
        return [module_path(config, stage, "processed") / s["subject"] / s["scan_id"] / atlas / kind /
                f"{s['scan_id']}_atlas-{atlas}_{suffix}.csv"
                for s in scans for atlas in config["atlases"]
                for kind, suffix in (("raw", "fc"), ("fisher_z", "fc_fisher_z"))]
    paths = [module_path(config, stage, "interim") / "dataset_description.json"]
    paths.extend(module_path(config, stage, "interim") / f"{subject}.html" for subject in sorted({scan["subject"] for scan in scans}))
    for scan in scans:
        if stage == "fmriprep":
            for suffix in (
                "space-fsLR_den-91k_bold.dtseries.nii",
                "space-MNI152NLin2009cAsym_desc-preproc_bold.nii.gz",
                "desc-confounds_timeseries.tsv",
            ):
                paths.append(derivative_path(config, scan, stage, suffix))
        elif stage == "xcpd":
            paths.append(derivative_path(config, scan, stage, "space-fsLR_den-91k_desc-denoised_bold.dtseries.nii"))
            for atlas in config["atlases"]:
                paths.append(derivative_path(config, scan, stage, f"space-fsLR_atlas-{atlas}_den-91k_stat-mean_timeseries.ptseries.nii"))
            if config.get("scope") == "task":
                paths.append(derivative_path(config, scan, stage, "design.tsv"))
    return paths


def validate_time_axes(config: dict, stage: str, scans: list[dict]) -> None:
    """Check source/confounds/CIFTI volume alignment, atlas axes and parcel signal validity."""
    import nibabel as nib
    from nibabel.cifti2 import SeriesAxis

    for scan in scans:
        frames = nib.load(scan["source_bold"]).shape[3]
        if stage == "fmriprep" and "slicetiming" not in config["fmriprep"]["ignore"]:
            metadata_path = derivative_path(config, scan, stage, "space-MNI152NLin2009cAsym_desc-preproc_bold.json")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            assert metadata["SliceTimingCorrected"] is True, f"STC was not performed: {scan['scan_id']}"
        confounds = derivative_path(config, scan, "fmriprep", "desc-confounds_timeseries.tsv")
        with confounds.open(encoding="utf-8-sig") as stream:
            records = list(csv.DictReader(stream, delimiter="\t"))
        assert len(records) == frames, f"BOLD/confounds volume mismatch: {scan['scan_id']}"
        suffix = "space-fsLR_den-91k_bold.dtseries.nii" if stage == "fmriprep" else "space-fsLR_den-91k_desc-denoised_bold.dtseries.nii"
        image = nib.load(derivative_path(config, scan, stage, suffix))
        axis = image.header.get_axis(0)
        expected = frames if stage == "fmriprep" else frames - config["xcpd"]["dummy_scans"]
        assert isinstance(axis, SeriesAxis) and axis.size == expected, f"CIFTI time axis mismatch: {scan['scan_id']}"
        if stage == "xcpd":
            if config.get("scope") == "task":
                source_json = Path(scan["source_bold"]).with_name(scan["scan_id"] + "_bold.json")
                tr = json.loads(source_json.read_text(encoding="utf-8"))["RepetitionTime"]
                assert axis.unit == "SECOND" and abs(axis.step - tr) < 1e-6, (
                    f"Task residual TR differs from source BOLD: {scan['scan_id']}")
            for atlas, parcels in config["atlases"].items():
                path = derivative_path(config, scan, stage, f"space-fsLR_atlas-{atlas}_den-91k_stat-mean_timeseries.ptseries.nii")
                data, _, step = load_ptseries(path, parcels)
                assert data.shape[0] == expected and abs(step - axis.step) < 1e-6, f"Parcellated time axis mismatch: {path}"


def check(config: dict, stage: str, scans: list[dict]) -> None:
    """Export complete and incomplete subjects with missing-product reasons; no silent exclusions."""
    rows = []
    for subject in sorted({scan["subject"] for scan in scans}):
        subset = [scan for scan in scans if scan["subject"] == subject]
        missing = [str(path) for path in required_products(config, stage, subset) if not path.is_file()]
        marker = record_path(config, stage, subject)
        reason = []
        if not marker.is_file():
            reason.append("no successful execution record")
        else:
            record = json.loads(marker.read_text(encoding="utf-8"))
            if record["processing"] != processing_settings(config, stage) or record["scans"] != subset:
                reason.append("processing settings or input run identities changed")
            for stage_before in UPSTREAM[stage]:
                previous = assert_completed(config, stage_before, subject, scans)
                if record["upstream_completed_at"][stage_before] != previous["completed_at_utc"]:
                    reason.append(f"{stage_before} was rerun after this {stage} execution")
            if stage == "xcpd" and config.get("scope") == "task":
                current = validate_background_inputs(config, subset)
                if record["task_confounds"] != current:
                    reason.append("task confounds changed after this xcpd execution")
        if missing:
            reason.append("missing products: " + ";".join(missing))
        if not reason:
            if stage == "background_fc":
                validate_background_fc(config, subset)
            else:
                validate_time_axes(config, stage, subset)
                if config.get("scope") == "task" and stage == "xcpd":
                    validate_joint_design(config, subset)
        rows.append(dict(dataset=config["dataset"], subject=subject, complete=str(not reason).lower(), reason=";".join(reason)))
    root = module_path(config, stage, "logs")
    write_csv(root / "completion_audit.csv", rows)
    for label, state in [("success", "true"), ("failed", "false")]:
        (root / f"subjects_{label}.txt").write_text(
            "".join(row["subject"] + "\n" for row in rows if row["complete"] == state), encoding="utf-8"
        )
    print(f"{stage}: {sum(row['complete'] == 'true' for row in rows)}/{len(rows)} complete; audit={root / 'completion_audit.csv'}")


def start_container(config: dict, stage: str, subject: str, scans: list[dict]) -> None:
    """Require the prepared input and current upstream output before the shell runs a container."""
    assert any(scan["subject"] == subject for scan in scans), f"Unknown subject: {subject}"
    for previous in UPSTREAM[stage]:
        assert_completed(config, previous, subject, scans)
    record_path(config, stage, subject).unlink(missing_ok=True)
    if config.get("scope") == "task" and stage == "xcpd":
        subset = [s for s in scans if s["subject"] == subject]
        current = validate_background_inputs(config, subset)
        # Verify the filter that the actual container will consume, not only a dry-run string.
        query_path = module_path(config, "xcpd", "logs") / "filters" / f"{subject}.json"
        query = json.loads(query_path.read_text(encoding="utf-8"))
        expected_runs = [int(s["run"]) for s in subset if s["run"]]
        assert query == {"bold": {"task": config["task"], "run": expected_runs or None}}, "Stale task BIDS filter"
        path = module_path(config, "xcpd", "logs") / "started" / f"{subject}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = dict(task_confounds=current, processing=processing_settings(config, stage), scans=subset,
                        upstream_completed_at=assert_completed(config, "fmriprep", subject, scans)["completed_at_utc"])
        path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")


def finish_container(config: dict, stage: str, subject: str, scans: list[dict], command: list[str], version: str) -> None:
    """Audit shell-produced derivatives before recording their actual command and successful completion."""
    subset = [scan for scan in scans if scan["subject"] == subject]
    assert subset, f"Unknown subject: {subject}"
    missing = [path for path in required_products(config, stage, subset) if not path.is_file()]
    assert not missing, f"Container exited but expected derivatives are missing: {missing}"
    validate_time_axes(config, stage, subset)
    if config.get("scope") == "task" and stage == "xcpd":
        current = validate_background_inputs(config, subset)
        path = module_path(config, "xcpd", "logs") / "started" / f"{subject}.json"
        started = json.loads(path.read_text(encoding="utf-8"))
        assert started == dict(task_confounds=current, processing=processing_settings(config, stage), scans=subset,
                               upstream_completed_at=assert_completed(config, "fmriprep", subject, scans)["completed_at_utc"]), (
            "Task design, settings or upstream changed during XCP-D; completion was not recorded")
        validate_joint_design(config, subset)
    save_record(config, stage, subject, scans, command, version)


def run_stage(config: dict, stage: str, subject: str, scans: list[dict], dry_run: bool,
              config_path: Path = Path("configs/neuroimaging_stc.json")) -> None:
    """Run scientific shell scripts for preprocessing, or Python calculations for head motion and FC."""
    assert any(scan["subject"] == subject for scan in scans), f"Unknown subject: {subject}"
    if stage in ("fmriprep", "xcpd"):
        script_name = f"run_{stage}.sbatch"
        if config.get("scope") == "task":
            script_name = "run_fmriprep_task.sbatch" if stage == "fmriprep" else "run_xcpd_task_background.sbatch"
        script = Path(config["project_root"]) / "scripts/neuroimaging" / script_name
        command = ["bash", str(script), config["dataset"], subject,
                   str(config_path.resolve()), config["project_root"]]
        if config.get("scope") == "task" and stage == "xcpd":
            command.append(config["task"])
        if dry_run:
            command.append("--dry-run")
        subprocess.run(command, check=True)
        return
    if dry_run:
        print(f"{stage}: dataset={config['dataset']}, subject={subject}, root={config['project_root']}")
        return
    for previous in UPSTREAM[stage]:
        assert_completed(config, previous, subject, scans)
    if stage == "rest_fc":
        assert_qc_current(config, scans)
    locks = module_path(config, stage, "logs") / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    lock = locks / (subject + ".lock")
    lock.mkdir()
    record_path(config, stage, subject).unlink(missing_ok=True)
    try:
        import nibabel
        import numpy
        if stage == "head_motion":
            compute_motion(config, scans, subject)
        elif stage == "background_fc":
            validate_time_axes(config, "xcpd", [s for s in scans if s["subject"] == subject])
            compute_background_fc(config, scans, subject)
        else:
            compute_fc(config, scans, subject)
        version = f"numpy={numpy.__version__}, nibabel={nibabel.__version__}"
        save_record(config, stage, subject, scans, sys.argv, version)
    finally:
        lock.rmdir()


def submit(config: dict, stage: str, config_path: Path, scans: list[dict], subjects_file: Path | None, dry_run: bool) -> None:
    """Submit fMRIPrep as a throttled subject array; keep individual jobs for downstream stages."""
    if stage == "rest_fc":
        assert_qc_current(config, scans)
    if subjects_file:
        subjects = [line.strip() for line in subjects_file.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    elif stage == "fmriprep" or config.get("scope") == "task":
        subjects = sorted({scan["subject"] for scan in scans})
    elif stage in ("xcpd", "head_motion"):
        previous = "fmriprep" if stage == "xcpd" else "xcpd"
        subjects = (module_path(config, previous, "logs") / "subjects_success.txt").read_text(encoding="utf-8").splitlines()
    else:
        subjects = [row["subject"] for row in read_csv(module_path(config, "head_motion", "tables") / "subject_qc.csv") if row["subject_valid"] == "true"]
    assert subjects and len(subjects) == len(set(subjects)), "No eligible subjects or duplicate subjects"
    assert set(subjects) <= {row["subject"] for row in scans}, "Submission subject missing from input inventory"
    if stage in ("xcpd", "head_motion", "rest_fc", "background_fc"):
        for subject in subjects:
            for previous in UPSTREAM[stage]:
                assert_completed(config, previous, subject, scans)
            if config.get("scope") == "task" and stage == "xcpd":
                validate_background_inputs(config, [s for s in scans if s["subject"] == subject])
    root = Path(config["project_root"])
    logs = module_path(config, stage, "logs")
    if not dry_run:
        logs.mkdir(parents=True, exist_ok=True)
    submitted = []
    script = root / "scripts/neuroimaging" / f"run_{stage}.sbatch"
    if config.get("scope", "rest") == "task":
        names = {"fmriprep": "run_fmriprep_task.sbatch", "xcpd": "run_xcpd_task_background.sbatch",
                 "head_motion": "run_head_motion_task_background.sbatch", "background_fc": "run_background_fc.sbatch"}
        script = root / "scripts/neuroimaging" / names[stage]
    if stage == "fmriprep":
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
        subjects_path = logs / f"array_subjects_{stamp}.txt"
        command = [
            "sbatch", "--parsable", "--chdir", str(root), "--partition", config["slurm"]["partition"],
            "--cpus-per-task", str(config["slurm"]["fmriprep_cpus"]),
            "--qos", config["slurm"]["fmriprep_qos"],
            "--array", f"0-{len(subjects)-1}%{config['slurm']['fmriprep_max_concurrent']}",
            "--output", str(logs / "array_%A_%a.out"), "--error", str(logs / "array_%A_%a.err"),
            str(script), config["dataset"], "--array", str(config_path.resolve()), str(root), str(subjects_path),
        ]
        if dry_run:
            print(shlex.join(command))
        else:
            # Freeze the selected order before submission; later prepare/subset edits cannot remap tasks.
            with subjects_path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write("\n".join(subjects) + "\n")
            job = subprocess.check_output(command, text=True).strip().split(";")[0]
            submitted = [dict(dataset=config["dataset"], subject=subject, job_id=f"{job}_{index}",
                              command=shlex.join(command)) for index, subject in enumerate(subjects)]
            write_csv(logs / f"submitted_{stamp}.csv", submitted)
            print(f"Submitted fMRIPrep array {job}: {len(subjects)} subjects, "
                  f"max concurrent={config['slurm']['fmriprep_max_concurrent']}")
        return
    for subject in subjects:
        command = [
            "sbatch", "--parsable", "--chdir", str(root), "--partition", config["slurm"]["partition"],
            "--cpus-per-task", str(config["slurm"][stage + "_cpus"]),
            "--output", str(logs / f"{subject}_%j.out"), "--error", str(logs / f"{subject}_%j.err"),
            str(script), config["dataset"], subject, str(config_path.resolve()),
        ]
        if config.get("scope") == "task":
            command.extend([str(root), config["task"]])
        if dry_run:
            print(shlex.join(command))
        else:
            job = subprocess.check_output(command, text=True).strip()
            submitted.append(dict(dataset=config["dataset"], subject=subject, job_id=job, command=shlex.join(command)))
            # Persist each successful submission if a later sbatch fails.
            write_csv(logs / f"submitted_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}.csv", [submitted[-1]])


def main() -> None:
    parser = argparse.ArgumentParser(description="EFNY fMRIPrep, rest FC and task background FC pipeline.")
    parser.add_argument("command", choices=["prepare", "submit", "run", "check", "qc", "export-motion-qc", "show-config", "shell-config", "start-container", "finish-container"])
    parser.add_argument("--config", type=Path, default=Path("configs/neuroimaging_stc.json"))
    parser.add_argument("--scope", choices=["rest", "task"], default="rest")
    parser.add_argument("--task", choices=["sst", "nback", "switch"], help="One task for the task-background branch.")
    parser.add_argument("--dataset", choices=["THU", "XY"], default="THU")
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--stage", choices=STAGES)
    parser.add_argument("--subject")
    parser.add_argument("--subjects", type=Path, help="Explicit sub-ID list; subset submission or input selection.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--tool-version")
    parser.add_argument("--container-command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    config = load_config(args.config, args.dataset, args.project_root, args.scope, args.task)
    if args.scope == "task":
        assert not config["fmriprep"]["ignore"], "Task primary analysis requires STC with an empty ignore list"
        assert args.stage != "rest_fc", "Use background_fc for task data"
        assert args.command not in ("qc", "export-motion-qc"), "Motion QC/FC rules are rest-only"
        if args.stage in ("xcpd", "head_motion", "background_fc"):
            assert args.dataset == "THU" and args.task, "Task background processing requires THU and --task"
            assert config["xcpd"]["dummy_scans"] == 0, "Task background analysis retains all acquired volumes"
            assert config["xcpd"]["nuisance_regressors"] == "36P", "Task background analysis extends 36P"
        else:
            assert args.task is None, "Task fMRIPrep continues to use the full configured task list"
    else:
        assert args.stage != "background_fc", "background_fc requires --scope task"
    assert isinstance(config["xcpd"]["dummy_scans"], int) and config["xcpd"]["dummy_scans"] >= 0
    if args.command == "show-config":
        print(json.dumps(config, indent=2))
    elif args.command == "shell-config":
        assert args.stage in ("fmriprep", "xcpd") and args.subject
        shell_config(config, args.stage, args.subject)
    elif args.command == "prepare":
        if args.scope == "task" and args.stage == "xcpd":
            prepare_background(config, input_scans(config), args.subjects)
        else:
            assert args.stage in (None, "fmriprep"), "Prepare the task background branch with --stage xcpd"
            prepare(config, args.subjects)
    else:
        scans = (background_scans(config) if args.scope == "task" and args.stage != "fmriprep" else input_scans(config))
        if args.command == "export-motion-qc":
            rows = read_csv(module_path(config, "head_motion", "tables") / "run_qc.csv")
            expected = {(scan["subject"], scan["scan_id"]) for scan in scans}
            observed = [(row["subject"], row["scan_id"]) for row in rows]
            assert len(observed) == len(set(observed)) and set(observed) == expected, "QC scan identities differ"
            write_motion_qc_tables(config, rows)
            print(f"{config['dataset']}: exported existing QC for {len({row['subject'] for row in rows})} subjects")
        elif args.command == "qc":
            current = {subject: assert_completed(config, "head_motion", subject, scans)["completed_at_utc"]
                       for subject in sorted({scan["subject"] for scan in scans})}
            summarize_qc(config, scans)
            (module_path(config, "head_motion", "logs") / "qc_provenance.json").write_text(
                json.dumps(dict(settings=config["head_motion"], head_motion_completed_at=current), indent=2) + "\n",
                encoding="utf-8",
            )
        elif args.command == "submit":
            assert args.stage, "submit requires --stage"
            submit(config, args.stage, args.config, scans, args.subjects, args.dry_run)
        elif args.command == "check":
            assert args.stage in ("fmriprep", "xcpd", "background_fc"), "check supports container stages and background_fc"
            if args.subject:
                scans = [scan for scan in scans if scan["subject"] == args.subject]
                assert scans, "Unknown subject"
            check(config, args.stage, scans)
        elif args.command == "start-container":
            assert args.stage in ("fmriprep", "xcpd") and args.subject
            start_container(config, args.stage, args.subject, scans)
        elif args.command == "finish-container":
            assert args.stage in ("fmriprep", "xcpd") and args.subject
            assert args.container_command and args.tool_version
            finish_container(config, args.stage, args.subject, scans, args.container_command, args.tool_version)
        elif args.command == "run":
            assert args.stage and args.subject, "run requires --stage and --subject"
            run_stage(config, args.stage, args.subject, scans, args.dry_run, args.config)


if __name__ == "__main__":
    main()
