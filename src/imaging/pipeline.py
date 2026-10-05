"""Explicit THU/XY rest preprocessing, Slurm submission and completion audits."""

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

from imaging.config import load_config, module_path
from imaging.rest import compute_fc, compute_motion, derivative_path, load_ptseries, read_csv, summarize_qc, write_csv


STAGES = ("fmriprep", "xcpd", "head_motion", "rest_fc")
UPSTREAM = {"fmriprep": (), "xcpd": ("fmriprep",), "head_motion": ("xcpd",), "rest_fc": ("xcpd", "head_motion")}


def discover_scans(config: dict, subjects_file: Path | None) -> list[dict]:
    """Inventory no-session, single-echo rest BOLD runs without inferring missing entities."""
    bids = Path(config["bids_dir"])
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
        for path in sorted((subject_dir / "func").glob(f"{subject}_task-rest*_bold.nii*")):
            stem = path.name.removesuffix(".gz").removesuffix(".nii")
            entities = dict(token.split("-", 1) for token in stem.split("_")[:-1])
            if entities["task"] != "rest":
                continue
            assert "ses" not in entities and "echo" not in entities, f"Unsupported session/echo: {path}"
            assert entities["run"].isdigit() and int(entities["run"]) > 0, f"Expected numeric run: {path}"
            subject_scans.append(dict(
                dataset=config["dataset"], subject=subject, run=entities["run"],
                scan_id=stem.removesuffix("_bold"), func_dir="func", source_bold=str(path),
            ))
        assert subject_scans, f"No task-rest run-* BOLD scans: {subject}"
        assert len({int(row["run"]) for row in subject_scans}) == len(subject_scans), (
            f"Repeated rest run numbers: {subject}"
        )
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
    print(f"Prepared {len(scans)} rest runs for {len({row['subject'] for row in scans})} {config['dataset']} subjects")


def input_scans(config: dict) -> list[dict]:
    scans = read_csv(module_path(config, "fmriprep", "logs") / "input_scans.csv")
    assert scans and all(row["dataset"] == config["dataset"] for row in scans)
    expected_bids = Path(config["bids_dir"])
    assert all(Path(row["source_bold"]).is_relative_to(expected_bids) for row in scans), (
        "Input BIDS root changed; prepare the dataset again"
    )
    return scans


def processing_settings(config: dict, stage: str) -> dict:
    """Describe scientific settings used to reject stale completion records."""
    keys = {
        "fmriprep": ("fmriprep",), "xcpd": ("xcpd", "atlases"),
        "head_motion": ("head_motion", "xcpd"), "rest_fc": ("head_motion", "xcpd", "atlases"),
    }[stage]
    settings = {key: config[key] for key in keys}
    if stage in ("fmriprep", "xcpd"):
        settings["image"] = config["tools"][stage + "_image"]
    return settings


def record_path(config: dict, stage: str, subject: str) -> Path:
    return module_path(config, stage, "logs") / "completed" / f"{subject}.json"


def assert_completed(config: dict, stage: str, subject: str, scans: list[dict]) -> dict:
    """Reject outputs whose scientific settings, input identities or upstream run have changed."""
    record = json.loads(record_path(config, stage, subject).read_text(encoding="utf-8"))
    assert record["processing"] == processing_settings(config, stage), f"Stale {stage} settings: {subject}"
    assert record["scans"] == [scan for scan in scans if scan["subject"] == subject], f"Stale {stage} inputs: {subject}"
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
    path = record_path(config, stage, subject)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def required_products(config: dict, stage: str, scans: list[dict]) -> list[Path]:
    """List the products required for this exact source inventory, not old log messages."""
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
    return paths


def validate_time_axes(config: dict, stage: str, scans: list[dict]) -> None:
    """Check source/confounds/CIFTI volume alignment, atlas axes and parcel signal validity."""
    import nibabel as nib
    from nibabel.cifti2 import SeriesAxis

    for scan in scans:
        frames = nib.load(scan["source_bold"]).shape[3]
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
            if stage == "xcpd":
                previous = assert_completed(config, "fmriprep", subject, scans)
                if record["upstream_completed_at"]["fmriprep"] != previous["completed_at_utc"]:
                    reason.append("fmriprep was rerun after this xcpd execution")
        if missing:
            reason.append("missing products: " + ";".join(missing))
        if not reason:
            validate_time_axes(config, stage, subset)
        rows.append(dict(dataset=config["dataset"], subject=subject, complete=str(not reason).lower(), reason=";".join(reason)))
    root = module_path(config, stage, "logs")
    write_csv(root / "completion_audit.csv", rows)
    for label, state in [("success", "true"), ("failed", "false")]:
        (root / f"subjects_{label}.txt").write_text(
            "".join(row["subject"] + "\n" for row in rows if row["complete"] == state), encoding="utf-8"
        )
    print(f"{stage}: {sum(row['complete'] == 'true' for row in rows)}/{len(rows)} complete; audit={root / 'completion_audit.csv'}")


def container_command(config: dict, stage: str, subject: str, cpus: int) -> tuple[list[str], dict]:
    """Build pinned rest container commands with read-only inputs and module-owned work paths."""
    tools = config["tools"]
    output = module_path(config, stage, "interim")
    work = output.parent / "work" / subject
    temporary = module_path(config, stage, "temp") / subject / os.environ.get("SLURM_JOB_ID", "manual")
    freesurfer = Path(config["project_root"]) / "data/interim/neuroimaging/freesurfer" / config["dataset"]
    binds = [
        (work, "/wd", "rw"), (temporary, "/tmp", "rw"),
        (output, "/output", "rw"), (Path(tools["fs_license"]), "/fs_license/license.txt", "ro"),
        (Path(tools["templateflow"]), "/templateflow", "ro"),
    ]
    command = ["singularity", "run", "--cleanenv"]
    if stage == "fmriprep":
        binds += [(Path(config["bids_dir"]), "/BIDS", "ro"), (freesurfer, "/freesurfer", "rw")]
        arguments = [
            "/BIDS", "/output", "participant", "--participant-label", subject.removeprefix("sub-"),
            "--task-id", "rest", "--fs-subjects-dir", "/freesurfer",
            "--fs-license-file", "/fs_license/license.txt", "--output-spaces",
            *config["fmriprep"]["output_spaces"], "--cifti-output", "91k",
            "--nprocs", str(cpus), "--omp-nthreads", "1", "--return-all-components",
            "--random-seed", str(config["fmriprep"]["random_seed"]),
            "--output-layout", "bids", "--notrack", "--stop-on-first-crash", "-w", "/wd",
        ]
    else:
        binds += [(module_path(config, "fmriprep", "interim"), "/fmriprep", "ro"), (freesurfer, "/freesurfer", "ro")]
        settings = config["xcpd"]
        arguments = [
            "/fmriprep", "/output", "participant", "--participant-label", subject.removeprefix("sub-"),
            "--input-type", "fmriprep", "--mode", "none", "--task-id", "rest",
            "--fs-license-file", "/fs_license/license.txt", "-w", "/wd",
            "--nprocs", str(cpus), "--omp-nthreads", "1",
            "--nuisance-regressors", settings["nuisance_regressors"],
            "--dummy-scans", str(settings["dummy_scans"]), "--smoothing", "0", "--despike", "n",
            "--file-format", "cifti", "--output-type", "censored", "--combine-runs", "n",
            "--warp-surfaces-native2std", "n", "--linc-qc", "n", "--abcc-qc", "n",
            "--min-coverage", str(settings["min_coverage"]), "--create-matrices", "all",
            "--output-run-wise-correlations", "y", "--head-radius", "auto",
            "--bpf-order", str(settings["bpf_order"]), "--lower-bpf", str(settings["lower_bpf_hz"]),
            "--upper-bpf", str(settings["upper_bpf_hz"]), "--motion-filter-type", settings["motion_filter_type"],
            "--band-stop-min", str(settings["motion_filter_bpm"]), "--fd-thresh", "0",
            "--atlases", *config["atlases"], "--output-layout", "bids", "--notrack",
            "--random-seed", str(settings["random_seed"]), "--stop-on-first-crash",
        ]
        atlas_arguments = []
        for name, host in tools["atlas_datasets"].items():
            container = f"/atlases/{name}"
            binds.append((Path(host), container, "ro"))
            atlas_arguments.append(f"{name}={container}")
        if atlas_arguments:
            arguments += ["--datasets", *atlas_arguments]
    for host, container, access in binds:
        command += ["-B", f"{host}:{container}:{access}"]
    command += [tools[stage + "_image"], *arguments]
    # Cleanenv alone does not override explicit SINGULARITYENV proxy variables inherited from a shell.
    environment = {key: value for key, value in os.environ.items() if "proxy" not in key.lower()}
    for key, value in dict(TEMPLATEFLOW_HOME="/templateflow", SUBJECTS_DIR="/freesurfer", TMPDIR="/tmp",
                           OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", NUMEXPR_NUM_THREADS="1").items():
        environment["SINGULARITYENV_" + key] = value
    return command, environment


def run_stage(config: dict, stage: str, subject: str, scans: list[dict], dry_run: bool) -> None:
    """Run one participant and write completion only after the required products are present."""
    subset = [scan for scan in scans if scan["subject"] == subject]
    assert subset, f"Subject absent from prepared inventory: {subject}"
    cpus = int(os.environ.get("SLURM_CPUS_PER_TASK", config["slurm"][stage + "_cpus"]))
    if stage in ("fmriprep", "xcpd"):
        command, environment = container_command(config, stage, subject, cpus)
        if dry_run:
            print(shlex.join(command))
            return
    elif dry_run:
        print(f"{stage}: dataset={config['dataset']}, subject={subject}, root={config['project_root']}")
        return
    for previous in UPSTREAM[stage]:
        assert_completed(config, previous, subject, scans)
    if stage == "rest_fc":
        assert_qc_current(config, scans)
    locks = module_path(config, stage, "logs") / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    lock = locks / (subject + ".lock")
    lock.mkdir()  # Prevent two jobs from writing one participant's derivatives.
    marker = record_path(config, stage, subject)
    marker.unlink(missing_ok=True)
    try:
        if stage in ("fmriprep", "xcpd"):
            root = module_path(config, stage, "interim")
            for path in [root, root.parent / "work" / subject,
                         module_path(config, stage, "temp") / subject / os.environ.get("SLURM_JOB_ID", "manual")]:
                path.mkdir(parents=True, exist_ok=True)
            if stage == "fmriprep":
                (Path(config["project_root"]) / "data/interim/neuroimaging/freesurfer" / config["dataset"]).mkdir(parents=True, exist_ok=True)
            version = subprocess.check_output(["singularity", "run", "--cleanenv", config["tools"][stage + "_image"], "--version"], env=environment, text=True).strip()
            print(shlex.join(command), flush=True)
            subprocess.run(command, env=environment, check=True)
            missing = [path for path in required_products(config, stage, subset) if not path.is_file()]
            assert not missing, f"Container exited but expected rest derivatives are missing: {missing}"
            validate_time_axes(config, stage, subset)
        else:
            import nibabel
            import numpy
            if stage == "head_motion":
                compute_motion(config, scans, subject)
            else:
                compute_fc(config, scans, subject)
            command = sys.argv
            version = f"numpy={numpy.__version__}, nibabel={nibabel.__version__}"
        save_record(config, stage, subject, scans, command, version)
    finally:
        lock.rmdir()


def submit(config: dict, stage: str, config_path: Path, scans: list[dict], subjects_file: Path | None, dry_run: bool) -> None:
    """Submit one Slurm job per eligible subject using explicit stage completion lists."""
    if stage == "rest_fc":
        assert_qc_current(config, scans)
    if subjects_file:
        subjects = [line.strip() for line in subjects_file.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    elif stage == "fmriprep":
        subjects = sorted({scan["subject"] for scan in scans})
    elif stage in ("xcpd", "head_motion"):
        previous = "fmriprep" if stage == "xcpd" else "xcpd"
        subjects = (module_path(config, previous, "logs") / "subjects_success.txt").read_text(encoding="utf-8").splitlines()
    else:
        subjects = [row["subject"] for row in read_csv(module_path(config, "head_motion", "tables") / "subject_qc.csv") if row["subject_valid"] == "true"]
    assert subjects and len(subjects) == len(set(subjects)), "No eligible subjects or duplicate subjects"
    assert set(subjects) <= {row["subject"] for row in scans}, "Submission subject missing from input inventory"
    if stage in ("xcpd", "head_motion", "rest_fc"):
        for subject in subjects:
            for previous in UPSTREAM[stage]:
                assert_completed(config, previous, subject, scans)
    root = Path(config["project_root"])
    logs = module_path(config, stage, "logs")
    if not dry_run:
        logs.mkdir(parents=True, exist_ok=True)
    submitted = []
    script = root / "scripts/neuroimaging" / f"run_{stage}.sbatch"
    for subject in subjects:
        command = [
            "sbatch", "--parsable", "--chdir", str(root), "--partition", config["slurm"]["partition"],
            "--cpus-per-task", str(config["slurm"][stage + "_cpus"]),
            "--output", str(logs / f"{subject}_%j.out"), "--error", str(logs / f"{subject}_%j.err"),
            str(script), config["dataset"], subject, str(config_path.resolve()),
        ]
        if dry_run:
            print(shlex.join(command))
        else:
            job = subprocess.check_output(command, text=True).strip()
            submitted.append(dict(dataset=config["dataset"], subject=subject, job_id=job, command=shlex.join(command)))
            # Persist each successful submission if a later sbatch fails.
            write_csv(logs / f"submitted_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}.csv", [submitted[-1]])


def main() -> None:
    parser = argparse.ArgumentParser(description="EFNY no-session, run-indexed rest neuroimaging pipeline.")
    parser.add_argument("command", choices=["prepare", "submit", "run", "check", "qc", "show-config"])
    parser.add_argument("--config", type=Path, default=Path("configs/neuroimaging.json"))
    parser.add_argument("--dataset", choices=["THU", "XY"], default="THU")
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--stage", choices=STAGES)
    parser.add_argument("--subject")
    parser.add_argument("--subjects", type=Path, help="Explicit sub-ID list; subset submission or input selection.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config, args.dataset, args.project_root)
    assert isinstance(config["xcpd"]["dummy_scans"], int) and config["xcpd"]["dummy_scans"] >= 0
    if args.command == "show-config":
        print(json.dumps(config, indent=2))
    elif args.command == "prepare":
        prepare(config, args.subjects)
    else:
        scans = input_scans(config)
        if args.command == "qc":
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
            assert args.stage in ("fmriprep", "xcpd"), "check supports container stages"
            if args.subject:
                scans = [scan for scan in scans if scan["subject"] == args.subject]
                assert scans, "Unknown subject"
            check(config, args.stage, scans)
        elif args.command == "run":
            assert args.stage and args.subject, "run requires --stage and --subject"
            run_stage(config, args.stage, args.subject, scans, args.dry_run)


if __name__ == "__main__":
    main()
