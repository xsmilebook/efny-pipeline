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
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from imaging.config import load_config, module_path
from imaging.pipeline import assert_completed, input_scans, prepare, validate_time_axes

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

# Preserve the complete submitted cohort before defining the authorized downstream scope.
full_subjects = sorted({scan["subject"] for scan in scans})
excluded = sorted(set(full_subjects) - set(subjects))
assert excluded == (fmriprep_logs / "reference_subjects_failed.txt").read_text().splitlines()
assert all(not list((Path(config["bids_dir"]) / subject / "anat").glob("*_T1w.nii*"))
           for subject in excluded), "An excluded subject now has T1w; review the scope"
for name in ("input_scans.csv", "subjects.txt", "resolved_config.json", "completion_audit.csv", "reference_audit.json"):
    path = fmriprep_logs / name
    archive = path.with_name(path.stem + "_original_batch" + path.suffix)
    assert not archive.exists(), f"Original cohort archive already exists: {archive}"
    shutil.copyfile(path, archive)
expected_scans = [scan for scan in scans if scan["subject"] in subjects]
prepare(config, fmriprep_logs / "reference_subjects_success.txt")
assert input_scans(config) == expected_scans, "Source run identities changed during cohort preparation"
scope = dict(original_subject_count=len(full_subjects), analysis_subject_count=len(subjects),
             excluded_subjects=excluded, exclusion_reason="Missing T1w; user explicitly elected no rerun",
             job_id=os.environ["SLURM_JOB_ID"], prepared_at_utc=datetime.now(timezone.utc).isoformat())
(fmriprep_logs / "downstream_scope.json").write_text(json.dumps(scope, indent=2) + "\n")

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
# Advance only after every subject job succeeds; the next job audits all products again.
dependency = "afterok:" + ":".join(row["job_id"].split(";")[0] for row in rows)
audit_command = ["sbatch", "--parsable", "--chdir", config["project_root"],
                 "--partition", config["slurm"]["partition"], "--cpus-per-task", "1",
                 "--dependency", dependency, "--kill-on-invalid-dep=yes", "--job-name", "efny_xcpd_audit_head_motion",
                 "--output", str(xcpd_logs / "audit_head_motion_%j.out"),
                 "--error", str(xcpd_logs / "audit_head_motion_%j.err"),
                 str(Path(config["project_root"]) / "scripts/neuroimaging/advance_rest_pipeline.sbatch"),
                 dataset, "xcpd"]
audit_job = subprocess.check_output(audit_command, text=True).strip().split(";")[0]
record.update(completed_at_utc=datetime.now(timezone.utc).isoformat(), submitted_subject_count=len(rows),
              downstream_audit_job_id=audit_job, downstream_audit_command=shlex.join(audit_command))
record_path.write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(record, indent=2), flush=True)
PY
