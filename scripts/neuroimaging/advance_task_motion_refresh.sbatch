#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH -p q_fat_c
set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
refresh="${1:?Refresh directory required}"
pilot_audit="${2:?Successful pilot audit job ID required}"
uv run --offline --no-sync python - "$refresh" "$pilot_audit" <<'PY'
"""Submit remaining motion jobs only after the three-run pilot audit succeeds."""
import csv
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path.cwd()
refresh = Path(sys.argv[1]).resolve()
pilot_audit = sys.argv[2]
assert refresh.parent == root / 'outputs/logs/neuroimaging/fmriprep/THU/task'
assert refresh.name.startswith('confounds_refresh_') and pilot_audit.isdigit()
receipt = json.loads((refresh / f'refresh_pilot_{pilot_audit}.json').read_text())
assert not receipt['apply'] and receipt['audit_completed_at_utc'] and receipt['runs'] == 3
record = json.loads((refresh / 'run.json').read_text())
assert receipt['subjects'] == [record['pilot_subject']]
assert not record.get('remaining_submitted_at_utc'), 'Remaining motion jobs were already launched'
assert not subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip()
statuses = subprocess.check_output(['sacct', '-X', '-j', pilot_audit,
    '--format=JobID,State,ExitCode', '-n', '-P'], text=True).splitlines()
assert len(statuses) == 1 and statuses[0].split('|')[1:3] == ['COMPLETED', '0:0'], statuses
record['remaining_submission_controller_job_id'] = os.environ['SLURM_JOB_ID']
record['remaining_submission_code_commit'] = subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip()
remaining = (refresh / 'subjects_remaining.txt').read_text().splitlines()
all_subjects = (refresh / 'subjects_all.txt').read_text().splitlines()
assert len(all_subjects) == len(set(all_subjects)) == 569
assert remaining == [s for s in all_subjects if s != record['pilot_subject']]
subprocess.run(['bash', 'scripts/neuroimaging/batch_run_recomputemotion.sh',
    record['input_root'], record['staging_root'], str(refresh / 'subjects_remaining.txt'),
    str(refresh / 'remaining')], check=True)
with (refresh / 'remaining/motion_submitted.tsv').open() as stream:
    rows = list(csv.DictReader(stream, delimiter='\t'))
with (refresh / 'pilot_current_jobs.tsv').open() as stream:
    pilots = list(csv.DictReader(stream, delimiter='\t'))
rows = pilots + rows
assert len(rows) == len(all_subjects) and {r['subject'] for r in rows} == set(all_subjects)
assert len({r['job_id'] for r in rows}) == len(rows)
job_file = refresh / 'motion_jobs_all.tsv'
with job_file.open('x', newline='') as stream:
    writer = csv.DictWriter(stream, fieldnames=['subject','job_id'], delimiter='\t')
    writer.writeheader()
    writer.writerows(rows)
record['remaining_submitted_at_utc'] = datetime.now(timezone.utc).isoformat()
record['motion_jobs_file'] = str(job_file)
(refresh / 'run.json').write_text(json.dumps(record, indent=2) + '\n')
command = ['sbatch','--parsable','--partition=q_fat_c','--cpus-per-task=3','--chdir='+str(root),
    '--dependency=afterok:' + ':'.join(row['job_id'] for row in rows), '--kill-on-invalid-dep=yes',
    '--job-name=thu_task_motion_apply', '--output='+str(refresh/'apply_%j.out'),
    '--error='+str(refresh/'apply_%j.err'), str(root/'scripts/neuroimaging/refresh_thu_task_confounds.sbatch'),
    '--refresh-root',str(refresh),'--jobs',str(job_file),'--apply']
job = subprocess.check_output(command,text=True).strip().split(';')[0]
record.update(apply_job_id=job, apply_command=shlex.join(command))
(refresh / 'run.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2),flush=True)
PY
