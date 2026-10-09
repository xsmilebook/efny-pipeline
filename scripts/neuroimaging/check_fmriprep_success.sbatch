#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH -p q_fat_c

set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"
dataset="${1:?Dataset required}"
reference="${2:?Reference check_fmriprep_success.sh required}"

# Execute the reference checker with project paths and underscore-style Slurm logs.
# Its report, log and per-source-run product criteria are unchanged.
uv run --offline --no-sync python - "$dataset" "$reference" <<'PY'
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from imaging.config import load_config, module_path

dataset, reference = sys.argv[1:]
config = load_config(Path("configs/neuroimaging.json"), dataset)
root = Path(config["project_root"])
logs = module_path(config, "fmriprep", "logs")
source = Path(reference).read_text()
replacements = {
    'PROJECT_ROOT="/ibmgpfs/cuizaixu_lab/xuhaoshu/projects/data_driven_EF"':
        f'PROJECT_ROOT={shlex.quote(str(root))}',
    'SUBLIST_FILE="${PROJECT_ROOT}/data/raw/${DATASET}/demo/bids_sublist.txt"':
        f'SUBLIST_FILE={shlex.quote(str(logs / "subjects.txt"))}',
    'SUCCESS_SUBLIST_FILE="${PROJECT_ROOT}/data/raw/${DATASET}/demo/sublist_fmriprep_success.txt"':
        f'SUCCESS_SUBLIST_FILE={shlex.quote(str(logs / "reference_subjects_success.txt"))}',
    'FAILED_SUBLIST_FILE="${PROJECT_ROOT}/data/raw/${DATASET}/demo/sublist_fmriprep_failed.txt"':
        f'FAILED_SUBLIST_FILE={shlex.quote(str(logs / "reference_subjects_failed.txt"))}',
    'BIDS_DIR="${PROJECT_ROOT}/data/raw/${DATASET}/neuroimaging/BIDS"':
        f'BIDS_DIR={shlex.quote(config["bids_dir"])}',
    'FMRIPREP_DIR="${PROJECT_ROOT}/data/interim/${DATASET}/neuroimaging/fmriprep/rest"':
        f'FMRIPREP_DIR={shlex.quote(str(module_path(config, "fmriprep", "interim")))}',
    'LOG_DIR="${PROJECT_ROOT}/outputs/logs/fmriprep/${DATASET}/rest"':
        f'LOG_DIR={shlex.quote(str(logs))}',
    '"${LOG_DIR}/${subj}".*':
        '"${LOG_DIR}/${subj}"_*.out "${LOG_DIR}/${subj}"_*.err',
}
for old, new in replacements.items():
    assert source.count(old) == 1, f"Reference checker changed: {old}"
    source = source.replace(old, new)
snapshot = logs / f"reference_checker_{os.environ['SLURM_JOB_ID']}.sh"
snapshot.write_text(source)
subprocess.run(["bash", str(snapshot), dataset], check=True)

# Add time-axis and provenance checks; do not replace the reference judgement.
subprocess.run(["uv", "run", "--offline", "--no-sync", "efny-imaging", "check",
                "--stage", "fmriprep", "--dataset", dataset], check=True)
reference_success = (logs / "reference_subjects_success.txt").read_text().splitlines()
reference_failed = (logs / "reference_subjects_failed.txt").read_text().splitlines()
assert reference_success == (logs / "subjects_success.txt").read_text().splitlines(), "Success criteria disagree"
assert reference_failed == (logs / "subjects_failed.txt").read_text().splitlines(), "Failure criteria disagree"
record = dict(reference=reference, adapted_script=str(snapshot), dataset=dataset,
              job_id=os.environ["SLURM_JOB_ID"], completed_at_utc=datetime.now(timezone.utc).isoformat(),
              code_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              tracked_worktree_dirty=bool(subprocess.check_output(
                  ["git", "status", "--porcelain", "--untracked-files=no"], text=True).strip()),
              reference_success_count=len(reference_success), reference_failed_count=len(reference_failed),
              reference_matches_product_and_time_axis_audit=True)
(logs / "reference_audit.json").write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(record, indent=2), flush=True)
PY
