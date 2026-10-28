#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH -p q_fat_c

set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"
phase="${1:?pilot, batch or audit required}"
registry="${2:?New or existing run registry JSON required}"
task="${3:-all}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
uv sync --check --offline --frozen --python 3.11 --python-platform x86_64-manylinux_2_17
if [[ "$phase" == batch ]]; then
    singularity_module=$(uv run --offline --no-sync python -c \
        'import json; print(json.load(open("configs/neuroimaging_stc.json"))["tools"]["singularity_module"])')
    module load "$singularity_module"
fi
uv run --offline --no-sync python - "$phase" "$registry" "$task" <<'PY'
"""Freeze prepared task scope, gate the batch on real pilots, and audit products."""
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from imaging.config import load_config, module_path
from imaging.pipeline import background_scans, check, submit
from imaging.rest import read_csv

phase, registry_name, selected_task = sys.argv[1:]
assert phase in ("pilot", "batch", "audit")
registry = Path(registry_name).resolve()
config_path = Path("configs/neuroimaging_stc.json").resolve()
configs = {task: load_config(config_path, "THU", scope="task", task=task)
           for task in ("sst", "nback", "switch")}
commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], text=True).strip()
assert not dirty, "Commit tracked changes before starting the task batch"


def save():
    """Persist job provenance after each submission so partial launches remain visible."""
    registry.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def schedule(next_phase, jobs, task="all"):
    """Advance only after every prerequisite exits successfully in Slurm."""
    log_dir = registry.parent
    command = ["sbatch", "--parsable", "--partition", "q_fat_c", "--cpus-per-task", "1",
               "--chdir", str(Path.cwd()), "--dependency", "afterok:" + ":".join(jobs),
               "--kill-on-invalid-dep=yes", "--job-name", f"thu_background_{next_phase}_{task}",
               "--output", str(log_dir / f"{next_phase}_{task}_%j.out"),
               "--error", str(log_dir / f"{next_phase}_{task}_%j.err"),
               str(Path.cwd() / "scripts/neuroimaging/submit_task_background.sbatch"),
               next_phase, str(registry), task]
    job = subprocess.check_output(command, text=True).strip().split(";")[0]
    record.setdefault("controllers", []).append(dict(phase=next_phase, task=task, job_id=job,
                                                    command=shlex.join(command)))
    save()


def launch(task, subjects, label):
    """Use the normal submission preflight and retain each successful sbatch receipt."""
    config = configs[task]
    logs = module_path(config, "xcpd", "logs")
    subject_file = registry.parent / f"{registry.stem}_{task}_{label}.txt"
    with subject_file.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("".join(subject + "\n" for subject in subjects))
    previous = set(logs.glob("submitted_*.csv"))
    submit(config, "xcpd", config_path, background_scans(config), subject_file, False)
    receipts = [row for path in sorted(set(logs.glob("submitted_*.csv")) - previous) for row in read_csv(path)]
    assert len(receipts) == len(subjects) and {row["subject"] for row in receipts} == set(subjects)
    record["tasks"][task][label + "_jobs"] = receipts
    save()
    return [row["job_id"].split(";")[0] for row in receipts]


def audit(task, subjects, label):
    """Require all frozen subjects to pass the real design and output time-axis audit."""
    config = configs[task]
    scans = [row for row in background_scans(config) if row["subject"] in subjects]
    assert {row["subject"] for row in scans} == set(subjects)
    check(config, "xcpd", scans)
    logs = module_path(config, "xcpd", "logs")
    rows = read_csv(logs / "completion_audit.csv")
    assert len(rows) == len(subjects) and all(row["complete"] == "true" for row in rows), rows
    (logs / f"{registry.stem}_{label}_audit.csv").write_text(
        (logs / "completion_audit.csv").read_text(encoding="utf-8"), encoding="utf-8")
    record["tasks"][task][label + "_audited_at_utc"] = datetime.now(timezone.utc).isoformat()
    save()


if phase == "pilot":
    assert not registry.exists(), "Use a new registry; do not duplicate a previous launch"
    record = dict(code_commit=commit, tracked_worktree_dirty=False, config=str(config_path),
                  prepared_job_dependency=os.environ.get("SLURM_JOB_DEPENDENCY", ""),
                  started_at_utc=datetime.now(timezone.utc).isoformat(),
                  pilot_controller_job_id=os.environ["SLURM_JOB_ID"], tasks={})
    # Validate all three scopes before any submission. Missing confounds remain explicit;
    # any available but scientifically invalid design stops the entire launch.
    for task, config in configs.items():
        logs = module_path(config, "xcpd", "logs")
        assert not list(logs.glob("submitted_*.csv")), f"Prior submissions exist: {logs}"
        assert not list((logs / "completed").glob("*.json")), f"Prior results exist: {logs}"
        assert not list((logs / "locks").glob("*.lock")), f"Active jobs exist: {logs}"
        rows = json.loads((logs / "confounds_audit.json").read_text(encoding="utf-8"))
        blocked = [row for row in rows if not row["ready"]]
        assert all(row["issues"] and all(issue.startswith("missing custom confounds: ")
                   for issue in row["issues"]) for row in blocked), blocked
        subjects = (logs / "subjects_ready.txt").read_text(encoding="utf-8").splitlines()
        assert subjects and len(subjects) == len(set(subjects))
        assert set(subjects) == {row["subject"] for row in rows if row["ready"]}
        # Cover each observed offset and SST cue protocol with a deterministic pilot.
        representatives = {}
        for row in sorted(rows, key=lambda r: r["scan_id"]):
            if row["subject"] in subjects:
                signature = (row["frame_offset_seconds"], "task_cue" in row["columns"] if task == "sst" else None)
                representatives.setdefault(signature, row["subject"])
        pilots = sorted(set(representatives.values()))
        record["tasks"][task] = dict(subjects=subjects, pilots=pilots, blocked_runs=blocked,
                                    ready_runs=sum(row["ready"] for row in rows),
                                    confounds_dir=config["task_xcpd"]["confounds_dir"],
                                    output_dir=str(module_path(config, "xcpd", "interim")))
    save()
    jobs = [job for task in configs for job in launch(task, record["tasks"][task]["pilots"], "pilot")]
    schedule("batch", jobs)
else:
    record = json.loads(registry.read_text(encoding="utf-8"))
    changed = subprocess.check_output(["git", "diff", record["code_commit"], "HEAD", "--",
                                       "src/imaging", "configs", "scripts/neuroimaging"], text=True)
    assert not changed, "Analysis code changed after pilot launch; review before advancing"
    if phase == "batch":
        assert not any("batch_jobs" in item for item in record["tasks"].values()), "Batch already launched"
        for task in configs:
            audit(task, record["tasks"][task]["pilots"], "pilot")
        # Use the installed XCP-D/Nilearn filter implementation to test whether
        # real residuals are orthogonal to the design after its actual filtering.
        root = Path.cwd()
        subprocess.run(["singularity", "exec", "--cleanenv", "-B", f"{root}:{root}:rw",
                        "--env", "OMP_NUM_THREADS=1,OPENBLAS_NUM_THREADS=1,MKL_NUM_THREADS=1",
                        configs["sst"]["tools"]["xcpd_image"], "python",
                        str(root / "scripts/neuroimaging/audit_task_pilot_residuals.py"),
                        str(registry)], check=True)
        # All tasks' pilots must pass before the first remaining subject is submitted.
        for task in configs:
            item = record["tasks"][task]
            remaining = [subject for subject in item["subjects"] if subject not in item["pilots"]]
            jobs = launch(task, remaining, "batch") if remaining else []
            schedule("audit", jobs or [row["job_id"].split(";")[0] for row in item["pilot_jobs"]], task)
    else:
        assert selected_task in configs
        # Each task writes its own audit; the common registry stays read-only here
        # because the three final audits may run concurrently.
        config = configs[selected_task]
        subjects = record["tasks"][selected_task]["subjects"]
        scans = [row for row in background_scans(config) if row["subject"] in subjects]
        check(config, "xcpd", scans)
        rows = read_csv(module_path(config, "xcpd", "logs") / "completion_audit.csv")
        assert {row["subject"] for row in rows} == set(subjects)
        assert all(row["complete"] == "true" for row in rows), rows
        print(f"{selected_task}: all {len(subjects)} frozen subjects passed the final XCP-D audit", flush=True)
print(json.dumps(record, indent=2), flush=True)
PY
