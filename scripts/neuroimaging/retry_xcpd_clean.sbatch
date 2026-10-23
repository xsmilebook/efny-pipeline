#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH -p q_fat_c

set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"
dataset="${1:?Dataset required}"
failed_manifest="${2:?Failed-job CSV required}"
other_jobs="${3:?Other unfinished-job IDs file required}"
mode="${4:-execute}"
terminal_state="${5:-FAILED}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
uv sync --check --offline --frozen --python 3.11 --python-platform x86_64-manylinux_2_17
uv run --offline --no-sync python - "$dataset" "$failed_manifest" "$other_jobs" "$mode" "$terminal_state" <<'PY'
import json
import os
import shlex
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from imaging.config import load_config, module_path
from imaging.pipeline import input_scans, submit
from imaging.rest import read_csv, write_csv

dataset, failed_manifest, other_jobs, mode, terminal_state = sys.argv[1:]
assert mode in ("execute", "dry-run"), mode
assert terminal_state in ("FAILED", "CANCELLED"), terminal_state
config_path = Path("configs/neuroimaging_stc.json").resolve()
config = load_config(config_path, dataset)
root = Path(config["project_root"]).resolve()
assert root == Path.cwd().resolve() and not config["fmriprep"]["ignore"]
scans = input_scans(config)
logs = module_path(config, "xcpd", "logs")
failed = read_csv(Path(failed_manifest))
subjects = sorted(row["subject"] for row in failed)
assert subjects and len(subjects) == len(set(subjects))
assert set(subjects) <= {scan["subject"] for scan in scans}
assert not any((logs / "completed" / f"{subject}.json").exists() for subject in subjects), "A selected subject completed"
old_ids = [row["job_id"].split(";")[0] for row in failed]
accounting = subprocess.check_output(["sacct", "-X", "-n", "-P", "-j", ",".join(old_ids),
                                      "--format=JobIDRaw,State%25,ExitCode"], text=True)
states = [line.split("|") for line in accounting.splitlines() if line.strip()]
assert {row[0] for row in states} == set(old_ids), states
if terminal_state == "FAILED":
    assert all(row[1:3] == ["FAILED", "1:0"] for row in states), states
else:
    # Explicitly requested cancellation must be complete before any selected cache is removed.
    assert all(row[1].split()[0] == "CANCELLED" for row in states), states
wait_ids = Path(other_jobs).read_text().splitlines()
assert all(job.isdigit() for job in wait_ids) and not set(wait_ids) & set(old_ids)
active = subprocess.check_output(["squeue", "-h", "-u", os.environ["USER"], "-n", "run_xcpd.sbatch", "-o", "%i"], text=True)
assert set(active.split()) <= set(wait_ids), "Unexpected active XCP-D jobs; review overlapping subjects"
output = module_path(config, "xcpd", "interim")
parents = [output, output.parent / "work", module_path(config, "xcpd", "temp")]
for parent in parents:
    assert not parent.is_symlink() and parent.resolve().is_relative_to(root) and parent.resolve() != root, parent
    assert "no_slicetiming" not in parent.parts and "task" not in parent.parts, parent
targets = [parent / subject for parent in parents for subject in subjects]
targets.extend(output / f"{subject}.html" for subject in subjects)
targets = [path for path in targets if path.exists() or path.is_symlink()]
assert all(not path.is_symlink() and path.resolve().parent in [p.resolve() for p in parents] for path in targets)
if mode == "dry-run":
    print(json.dumps(dict(subjects=subjects, cleanup_targets=list(map(str, targets)), other_unfinished_jobs=wait_ids), indent=2))
    sys.exit(0)
job = os.environ["SLURM_JOB_ID"]
record_root = logs / f"clean_retry_{job}"
record_root.mkdir()
record_path = record_root / "retry.json"
record = dict(job_id=job, started_at_utc=datetime.now(timezone.utc).isoformat(), failed_jobs=failed,
              unchanged_unfinished_jobs=wait_ids, cleanup_targets=list(map(str, targets)),
              code_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              worktree_dirty=bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
              resolved_config=config, workers=int(os.environ["SLURM_CPUS_PER_TASK"]),
              required_terminal_state=terminal_state, verified_job_states=states,
              analysis_parameters_changed=False, command=sys.argv)
record_path.write_text(json.dumps(record, indent=2) + "\n")
for subject in subjects:
    crash_logs = output / subject / "log"
    if crash_logs.exists():
        shutil.copytree(crash_logs, record_root / "previous_crash_logs" / subject)
    lock = logs / "locks" / f"{subject}.lock"
    if lock.exists():
        assert not lock.is_symlink() and lock.resolve().parent == (logs / "locks").resolve(), lock
        lock.rmdir()


def remove_partial(path: Path) -> str:
    """Discard only selected failed subjects' checked XCP-D products and restart caches."""
    subprocess.run(["rm", "--one-file-system", "-rf", "--", str(path)], check=True)
    assert not path.exists() and not path.is_symlink(), path
    return str(path)


with (record_root / "removed.jsonl").open("w") as stream:
    with ThreadPoolExecutor(max_workers=record["workers"]) as pool:
        for removed in pool.map(remove_partial, targets):
            stream.write(json.dumps(dict(removed=removed)) + "\n")
            stream.flush()
            print(f"Removed {removed}", flush=True)
record.update(cleanup_completed_at_utc=datetime.now(timezone.utc).isoformat(), removed_count=len(targets))
record_path.write_text(json.dumps(record, indent=2) + "\n")
subjects_path = record_root / "subjects.txt"
subjects_path.write_text("\n".join(subjects) + "\n")
previous_submissions = set(logs.glob("submitted_*.csv"))
submit(config, "xcpd", config_path, scans, subjects_path, False)
new_submissions = sorted(set(logs.glob("submitted_*.csv")) - previous_submissions)
rows = [row for path in new_submissions for row in read_csv(path)]
assert len(rows) == len(subjects) and {row["subject"] for row in rows} == set(subjects)
write_csv(record_root / "submitted.csv", rows)
record.update(submitted_subject_count=len(rows), new_jobs=rows)
record_path.write_text(json.dumps(record, indent=2) + "\n")
# The unmodified running jobs must also succeed before the full-cohort audit can advance.
dependency = "afterok:" + ":".join([row["job_id"].split(";")[0] for row in rows] + wait_ids)
command = ["sbatch", "--parsable", "--chdir", str(root), "--partition", config["slurm"]["partition"],
           "--cpus-per-task", "1", "--dependency", dependency, "--kill-on-invalid-dep=yes",
           "--job-name", "efny_xcpd_clean_audit", "--output", str(logs / "audit_clean_%j.out"),
           "--error", str(logs / "audit_clean_%j.err"),
           str(root / "scripts/neuroimaging/advance_rest_pipeline.sbatch"), dataset, "xcpd"]
audit_job = subprocess.check_output(command, text=True).strip().split(";")[0]
record.update(audit_job_id=audit_job, audit_command=shlex.join(command),
              completed_at_utc=datetime.now(timezone.utc).isoformat())
record_path.write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(dict(receipt=str(record_path), submitted_subjects=len(rows), audit_job_id=audit_job), indent=2), flush=True)
PY
