#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH -p q_fat_c

set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"
dataset="${1:?Dataset required}"
stage="${2:?Completed stage required: xcpd, head_motion or rest_fc}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1

# Run this job with afterok dependencies on all jobs of the completed stage.
uv run --offline --no-sync python - "$dataset" "$stage" <<'PY'
import csv
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import nibabel
import numpy as np

from imaging.config import load_config, module_path
from imaging.pipeline import assert_completed, assert_qc_current, input_scans
from imaging.rest import read_csv, write_csv

dataset, stage = sys.argv[1:]
assert stage in ("xcpd", "head_motion", "rest_fc"), stage
config = load_config(Path("configs/neuroimaging.json"), dataset)
root = Path(config["project_root"])
scans = input_scans(config)
subjects = sorted({scan["subject"] for scan in scans})
assert subjects == (module_path(config, "fmriprep", "logs") / "reference_subjects_success.txt").read_text().splitlines()
logs = module_path(config, stage, "logs")
record = dict(dataset=dataset, stage=stage, job_id=os.environ["SLURM_JOB_ID"], command=sys.argv,
              started_at_utc=datetime.now(timezone.utc).isoformat(), analysis_subject_count=len(subjects),
              code_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              tracked_worktree_dirty=bool(subprocess.check_output(
                  ["git", "status", "--porcelain", "--untracked-files=no"], text=True).strip()),
              resolved_config=config, numpy_version=np.__version__, nibabel_version=nibabel.__version__)
receipt = logs / f"advance_{os.environ['SLURM_JOB_ID']}.json"
receipt.write_text(json.dumps(record, indent=2) + "\n")

if stage == "xcpd":
    subprocess.run(["uv", "run", "--offline", "--no-sync", "efny-imaging", "check",
                    "--dataset", dataset, "--stage", "xcpd"], check=True)
    assert (logs / "subjects_success.txt").read_text().splitlines() == subjects, "Incomplete XCP-D cohort"
    assert not (logs / "subjects_failed.txt").read_text().strip(), "Failed XCP-D subjects remain"
    next_stage, next_audit = "head_motion", "head_motion"
elif stage == "head_motion":
    for subject in subjects:
        assert_completed(config, "head_motion", subject, scans)
    subprocess.run(["uv", "run", "--offline", "--no-sync", "efny-imaging", "qc", "--dataset", dataset], check=True)
    next_stage, next_audit = "rest_fc", "rest_fc"
else:
    assert_qc_current(config, scans)
    eligible = [row["subject"] for row in read_csv(module_path(config, "head_motion", "tables") / "subject_qc.csv")
                if row["subject_valid"] == "true"]
    run_qc = read_csv(module_path(config, "head_motion", "tables") / "run_qc.csv")
    rows = []
    for subject in eligible:
        assert_completed(config, "rest_fc", subject, scans)
        provenance = read_csv(module_path(config, "rest_fc", "tables") / "subjects" / f"{subject}.csv")
        assert {row["atlas"] for row in provenance} == set(config["atlases"])
        qc_runs = [row for row in run_qc
                   if row["subject"] == subject and row["run_valid"] == "true"]
        qc_runs.sort(key=lambda row: int(row["run"]))
        for atlas, parcels in config["atlases"].items():
            matrices = []
            for kind, suffix in (("raw", "fc"), ("fisher_z", "fc_fisher_z")):
                path = module_path(config, "rest_fc", "processed") / subject / atlas / kind / f"{subject}_atlas-{atlas}_{suffix}.csv"
                with path.open(newline="") as stream:
                    table = list(csv.reader(stream))
                labels = table[0][1:]
                assert len(labels) == len(set(labels)) == parcels and [row[0] for row in table[1:]] == labels, path
                matrix = np.array([row[1:] for row in table[1:]], dtype=float)
                assert matrix.shape == (parcels, parcels) and np.isfinite(matrix).all(), path
                assert np.allclose(matrix, matrix.T, rtol=0, atol=1e-10), path
                matrices.append((matrix, labels))
            correlation, labels = matrices[0]
            fisher, fisher_labels = matrices[1]
            assert labels == fisher_labels and np.allclose(np.diag(correlation), 1), subject
            assert np.max(np.abs(correlation)) <= 1 + 1e-10 and np.allclose(np.diag(fisher), 0), subject
            expected_z = np.arctanh(np.clip(correlation, -0.999999, 0.999999))
            np.fill_diagonal(expected_z, 0)
            assert np.allclose(fisher, expected_z, rtol=0, atol=1e-10), subject
            origin = [row for row in provenance if row["atlas"] == atlas]
            assert len(origin) == 1 and int(origin[0]["parcels"]) == parcels
            assert origin[0]["scan_ids"].split(";") == [row["scan_id"] for row in qc_runs]
            assert int(origin[0]["frames"]) == sum(int(row["frames"]) for row in qc_runs)
            rows.append(dict(dataset=dataset, subject=subject, atlas=atlas, parcels=parcels,
                             valid_runs=len(qc_runs), frames=origin[0]["frames"], complete="true"))
    assert rows, "No QC-qualified FC outputs"
    write_csv(logs / "completion_audit.csv", rows)
    record.update(completed_at_utc=datetime.now(timezone.utc).isoformat(),
                  qc_qualified_subject_count=len(eligible), validated_atlas_count=len(rows))
    receipt.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2), flush=True)
    sys.exit(0)

next_logs = module_path(config, next_stage, "logs")
next_logs.mkdir(parents=True, exist_ok=True)
assert not list(next_logs.glob("submitted_*.csv")), f"{next_stage} was already submitted"
assert not list((next_logs / "completed").glob("*.json")), f"Prior {next_stage} outputs exist"
subprocess.run(["uv", "run", "--offline", "--no-sync", "efny-imaging", "submit",
                "--dataset", dataset, "--stage", next_stage], check=True)
submitted = []
for path in sorted(next_logs.glob("submitted_*.csv")):
    submitted.extend(read_csv(path))
expected = subjects if next_stage == "head_motion" else [row["subject"] for row in
    read_csv(module_path(config, "head_motion", "tables") / "subject_qc.csv") if row["subject_valid"] == "true"]
assert len(submitted) == len(expected) and {row["subject"] for row in submitted} == set(expected)
write_csv(next_logs / "submission_batch.csv", submitted)
dependency = "afterok:" + ":".join(row["job_id"].split(";")[0] for row in submitted)
audit_command = ["sbatch", "--parsable", "--chdir", str(root),
                 "--partition", config["slurm"]["partition"], "--cpus-per-task", "1",
                 "--dependency", dependency, "--kill-on-invalid-dep=yes", "--job-name", f"efny_{next_audit}_audit",
                 "--output", str(next_logs / "advance_%j.out"), "--error", str(next_logs / "advance_%j.err"),
                 str(root / "scripts/neuroimaging/advance_rest_pipeline.sbatch"), dataset, next_audit]
audit_job = subprocess.check_output(audit_command, text=True).strip().split(";")[0]
record.update(completed_at_utc=datetime.now(timezone.utc).isoformat(), next_stage=next_stage,
              submitted_subject_count=len(submitted), next_audit_job_id=audit_job,
              next_audit_command=shlex.join(audit_command))
receipt.write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(record, indent=2), flush=True)
PY
