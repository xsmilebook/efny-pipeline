#!/bin/bash
#SBATCH --job-name=compFD
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=3
#SBATCH -p q_fat_c

module load singularity/3.7.0

# Task adaptation of the user-supplied brainproject script; the recomputation is unchanged.
# Usage: bash recompute_motion_25_2_7.sh SUBJECT OUT_DIRECTORY OLD_TASK_DIRECTORY
# Process all acquired task runs for the specified subject, including runs without task regressors.
set -euo pipefail

if [[ $# -ne 3 ]]; then
    echo "Usage: bash $0 SUBJECT OUT_DIRECTORY OLD_TASK_DIRECTORY" >&2
    exit 2
fi
subj="$1"
Out="$2"
OLD="$3"
[[ -n "$subj" && -n "$Out" ]] || { echo 'Both arguments are required.' >&2; exit 2; }

IMAGE='/ibmgpfs/cuizaixu_lab/xuhaoshu/packages/singularity/fmriprep-25.2.7.simg'
[[ "${OLD%/}" == */fmriprep/THU/task ]] || { echo 'Expected the THU task derivative root.' >&2; exit 2; }
mkdir -p "$Out"
[[ "$(readlink -f "$OLD")" != "$(readlink -f "$Out")" ]] || exit 1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export SINGULARITYENV_OMP_NUM_THREADS=1 SINGULARITYENV_OPENBLAS_NUM_THREADS=1
export SINGULARITYENV_MKL_NUM_THREADS=1 SINGULARITYENV_NUMEXPR_NUM_THREADS=1

singularity exec --cleanenv \
    --bind "$OLD:/old:ro" --bind "$Out:/out:rw" \
    "$IMAGE" python - "$subj" <<'PY'
import gzip, json, shutil, sys, tempfile
from pathlib import Path
import numpy as np
import pandas as pd
from fmriprep import __version__
from fmriprep.interfaces.confounds import FSLMotionParams, FramewiseDisplacement
from niworkflows.interfaces.confounds import ExpandModel, spike_regressors

# If the original fMRIPrep run used different spike thresholds, change these.
FD_THRESHOLD, DVARS_THRESHOLD = 0.5, 1.5
assert __version__.split('+')[0] == '25.2.7', 'Container must be fMRIPrep 25.2.7'
root, out = Path('/old'), Path('/out')
subject = sys.argv[1]
if subject and not subject.startswith('sub-'):
    subject = 'sub-' + subject

motion24 = [p + s for p in ('trans_x', 'trans_y', 'trans_z', 'rot_x', 'rot_y', 'rot_z')
            for s in ('', '_derivative1', '_power2', '_derivative1_power2')]
suffix = '_desc-confounds_timeseries.tsv'
files = sorted((root / subject / 'func').glob('*_task-*_desc-confounds_timeseries.tsv'))
assert all(p.name.split('_')[0] == subject and
           next(part for part in p.name.split('_') if part.startswith('task-'))
           in ('task-sst', 'task-nback', 'task-switch') for p in files)
if not files:
    raise SystemExit('No matching task confounds files found.')

failed = 0
for tsv in files:
    print(tsv.relative_to(root), flush=True)
    try:
        prefix = tsv.name[:-len(suffix)]
        refs = [p for p in tsv.parent.glob(prefix + '_desc-hmc_boldref.nii*')
                if p.is_file() and p.name.endswith(('.nii', '.nii.gz'))]
        xfms = [p for p in tsv.parent.glob(prefix + '_from-orig_to-boldref*_desc-hmc_xfm.txt*')
                if p.is_file() and p.name.endswith(('.txt', '.txt.gz'))]
        if len(refs) != 1 or len(xfms) != 1:
            raise RuntimeError('Need exactly one matching HMC reference and transform.')
        table = pd.read_csv(tsv, sep='\t', float_precision='round_trip')

        with tempfile.TemporaryDirectory(dir=str(out)) as work:
            xfm = xfms[0]
            if xfm.name.endswith('.gz'):
                unpacked = Path(work) / 'hmc_xfm.txt'
                with gzip.open(xfm, 'rb') as src, unpacked.open('wb') as dst:
                    shutil.copyfileobj(src, dst)
                xfm = unpacked

            motion_file = FSLMotionParams(
                xfm_file=str(xfm), boldref_file=str(refs[0])
            ).run(cwd=work).outputs.out_file
            motion = pd.read_csv(motion_file, sep='\t')
            if len(motion) != len(table) or len(table) == 0:
                raise RuntimeError('Motion and original confounds row counts differ.')
            if not np.isfinite(motion.to_numpy()).all():
                raise RuntimeError('Non-finite motion parameters.')
            fd_file = FramewiseDisplacement(
                in_file=motion_file, radius=50.0
            ).run(cwd=work).outputs.out_file
            expanded = ExpandModel(
                confounds_file=motion_file, model_formula='(dd1(rps))^^2'
            ).run(cwd=work).outputs.confounds_file

            # Replace 24 motion regressors plus FD; keep all other confounds.
            table[motion24] = pd.read_csv(expanded, sep='\t')[motion24]
            table['framewise_displacement'] = pd.read_csv(fd_file, sep='\t')['FramewiseDisplacement']

        # Regenerate motion_outlier columns because FD has changed.
        table = table.drop(columns=[c for c in table if c.startswith('motion_outlier')])
        table = spike_regressors(table, criteria={
            'framewise_displacement': ('>', FD_THRESHOLD),
            'std_dvars': ('>', DVARS_THRESHOLD)}, lags=[0])

        target = out / tsv.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix('.tsv.tmp')
        table.to_csv(temporary, sep='\t', index=False, na_rep='n/a')
        temporary.replace(target)

        # Preserve the original JSON, including CompCor component metadata.
        sidecar = tsv.with_suffix('.json')
        if sidecar.is_file():
            metadata = {k: v for k, v in json.loads(sidecar.read_text()).items()
                        if not k.startswith('motion_outlier')}
            for c in table:
                if c.startswith('motion_outlier'):
                    metadata[c] = {'Description': f'FD > {FD_THRESHOLD} mm or '
                                   f'standardized DVARS > {DVARS_THRESHOLD}.'}
            target.with_suffix('.json').write_text(
                json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
        print(f'  Saved: {target}', flush=True)
    except Exception as exc:
        failed += 1
        print(f'  FAILED: {exc}', file=sys.stderr, flush=True)

print(f'Done: {len(files) - failed} succeeded, {failed} failed.')
sys.exit(1 if failed else 0)
PY
