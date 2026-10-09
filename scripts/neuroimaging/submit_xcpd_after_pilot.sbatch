#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH -p q_fat_c

set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"
dataset="${1:?Dataset required}"
pilot="${2:?Pilot subject required}"

# This job must depend on afterok:<pilot_job>, never afterany.
uv run --offline --no-sync efny-imaging check --stage xcpd --dataset "$dataset" --subject "$pilot"
uv run --offline --no-sync python - "$dataset" "$pilot" <<'PY'
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from imaging.config import load_config, module_path
from imaging.pipeline import assert_completed, input_scans, validate_time_axes

dataset, pilot = sys.argv[1:]
config = load_config(Path("configs/neuroimaging.json"), dataset)
fmriprep_logs = module_path(config, "fmriprep", "logs")
xcpd_logs = module_path(config, "xcpd", "logs")
subjects = (fmriprep_logs / "reference_subjects_success.txt").read_text().splitlines()
assert subjects == (fmriprep_logs / "subjects_success.txt").read_text().splitlines()
assert pilot in subjects
scans = input_scans(config)
assert_completed(config, "xcpd", pilot, scans)
validate_time_axes(config, "xcpd", [scan for scan in scans if scan["subject"] == pilot])
assert {p.stem for p in (xcpd_logs / "completed").glob("*.json")} == {pilot}, "Unexpected prior XCP-D results"
assert not list((xcpd_logs / "locks").iterdir()), "Active XCP-D execution remains"
assert not list(xcpd_logs.glob("submitted_*.csv")), "Unexpected prior batch submissions"
remaining = xcpd_logs / "subjects_after_pilot.txt"
remaining.write_text("".join(subject + "\n" for subject in subjects if subject != pilot))
record = dict(dataset=dataset, pilot=pilot, remaining_subject_count=len(subjects)-1,
              job_id=os.environ["SLURM_JOB_ID"], started_at_utc=datetime.now(timezone.utc).isoformat(),
              code_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              tracked_worktree_dirty=bool(subprocess.check_output(
                  ["git", "status", "--porcelain", "--untracked-files=no"], text=True).strip()))
record_path = xcpd_logs / "batch_after_pilot.json"
record_path.write_text(json.dumps(record, indent=2) + "\n")
subprocess.run(["uv", "run", "--offline", "--no-sync", "efny-imaging", "submit",
                "--stage", "xcpd", "--dataset", dataset, "--subjects", str(remaining)], check=True)
rows = []
for path in sorted(xcpd_logs.glob("submitted_*.csv")):
    rows.extend(csv.DictReader(path.open()))
assert len(rows) == len(subjects)-1 and {row["subject"] for row in rows} == set(subjects)-{pilot}
with (xcpd_logs / "submission_batch_after_pilot.csv").open("w", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=["dataset", "subject", "job_id", "command"])
    writer.writeheader()
    writer.writerows(rows)
record.update(completed_at_utc=datetime.now(timezone.utc).isoformat(), submitted_subject_count=len(rows))
record_path.write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(record, indent=2), flush=True)
PY
