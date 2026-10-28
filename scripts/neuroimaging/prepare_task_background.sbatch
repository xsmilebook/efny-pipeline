#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH -p q_fat_c

set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"
dataset="${1:-THU}"
config="${2:-configs/neuroimaging_stc.json}"
project_root="${3:-$PWD}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
uv sync --check --offline --frozen --python 3.11 --python-platform x86_64-manylinux_2_17

# Audit the full upstream task inventory; missing or misaligned designs remain explicit.
for task in sst nback switch; do
    uv run --offline --no-sync efny-imaging prepare --stage xcpd --scope task \
        --task "$task" --dataset "$dataset" --config "$config" --project-root "$project_root"
done
