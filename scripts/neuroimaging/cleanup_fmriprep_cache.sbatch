#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH -p q_fat_c

set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"
dataset="${1:?Dataset required}"

# Only run after explicit authorization to discard all subjects' restart caches.
uv run --offline --no-sync python - "$dataset" <<'PY'
import csv
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from imaging.config import load_config, module_path

config = load_config(Path("configs/neuroimaging.json"), sys.argv[1])
root = Path(config["project_root"]).resolve()
logs = module_path(config, "fmriprep", "logs")
manifest = list(csv.DictReader((logs / "submission_batch_20261006_newroot.csv").open()))
job_ids = {row["job_id"].split(";")[0] for row in manifest}
active = set(subprocess.check_output(["squeue", "--noheader", "--user", os.environ["USER"],
                                     "--format=%i"], text=True).splitlines())
assert not (job_ids & active), "Batch still has active fMRIPrep jobs"
assert not list((logs / "locks").iterdir()), "fMRIPrep execution locks remain"

# Retain derivatives, FreeSurfer, logs and the empty cache roots.
cache_roots = [module_path(config, "fmriprep", "interim").parent / "work",
               module_path(config, "fmriprep", "temp")]
targets = []
for cache_root in cache_roots:
    assert not cache_root.is_symlink(), f"Cache root is a symlink: {cache_root}"
    resolved = cache_root.resolve()
    assert resolved.is_relative_to(root) and resolved != root, resolved
    for target in sorted(cache_root.iterdir()):
        assert target.name.startswith(config["datasets"][config["dataset"]]["subject_prefix"]), target
        assert target.is_dir() and not target.is_symlink() and target.resolve().parent == resolved, target
        targets.append(target)
workers = int(os.environ["SLURM_CPUS_PER_TASK"])
record = dict(dataset=config["dataset"], job_id=os.environ["SLURM_JOB_ID"], workers=workers,
              started_at_utc=datetime.now(timezone.utc).isoformat(), cache_roots=list(map(str, cache_roots)),
              targets=list(map(str, targets)),
              code_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              tracked_worktree_dirty=bool(subprocess.check_output(
                  ["git", "status", "--porcelain", "--untracked-files=no"], text=True).strip()),
              command=["rm", "--one-file-system", "-rf", "--", "<subject-cache-directory>"],
              discard_failed_subject_restart_caches_authorized=True)
record_path = logs / f"cache_cleanup_{os.environ['SLURM_JOB_ID']}.json"
record_path.write_text(json.dumps(record, indent=2) + "\n")
print(f"Deleting {len(targets)} subject cache directories with {workers} workers", flush=True)

def remove_cache(target: Path) -> str:
    """Remove one checked subject cache without following symlinks or filesystem mounts."""
    subprocess.run(["rm", "--one-file-system", "-rf", "--", str(target)], check=True)
    assert not target.exists(), f"Cache deletion incomplete: {target}"
    return str(target)

with (logs / f"cache_cleanup_{os.environ['SLURM_JOB_ID']}.jsonl").open("w") as stream:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for removed in pool.map(remove_cache, targets):
            stream.write(json.dumps(dict(removed=removed)) + "\n")
            stream.flush()
for cache_root in cache_roots:
    assert not list(cache_root.iterdir()), f"Cache root not empty: {cache_root}"
record.update(completed_at_utc=datetime.now(timezone.utc).isoformat(), removed_count=len(targets))
record_path.write_text(json.dumps(record, indent=2) + "\n")
print(f"Cache cleanup completed: {record_path}", flush=True)
PY
