#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=6
#SBATCH -p q_fat_c

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$(dirname "$(realpath "$0")")/../..}"
dataset="${1:?Dataset required}"
subject="${2:?Subject required}"
config="${3:-configs/neuroimaging.json}"
project_root="${4:-$PWD}"
cpus="${SLURM_CPUS_PER_TASK:-6}"

# Read shared paths and configured values; the scientific workflow is explicit below.
shell_values=$(uv run --offline --no-sync efny-imaging shell-config \
    --stage fmriprep --dataset "$dataset" --subject "$subject" \
    --config "$config" --project-root "$project_root")
eval "$shell_values"

command=(
    singularity run --cleanenv
    -B "${BIDS_DIR}:/BIDS:ro"
    -B "${OUTPUT_DIR}:/output:rw"
    -B "${WORK_DIR}:/wd:rw"
    -B "${TEMP_DIR}:/tmp:rw"
    -B "${FS_LICENSE}:/fs_license/license.txt:ro"
    -B "${FREESURFER_DIR}:/freesurfer:rw"
    -B "${TEMPLATEFLOW}:/templateflow:ro"
    "$IMAGE"
    /BIDS /output participant
    --participant-label "${subject#sub-}"
    --task-id rest
    --fs-subjects-dir /freesurfer
    --fs-license-file /fs_license/license.txt
    --output-spaces "${FMRIPREP_OUTPUT_SPACES[@]}"
    --cifti-output 91k
    --nprocs "$cpus"
    --omp-nthreads 1
    --return-all-components
    --random-seed "$FMRIPREP_RANDOM_SEED"
    --output-layout bids
    --notrack
    --stop-on-first-crash
    -w /wd
)

if [[ "${5:-}" == --dry-run ]]; then
    printf '%q ' "${command[@]}"
    printf '\n'
    exit 0
fi

export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
uv sync --check --offline --frozen --python 3.11 --python-platform x86_64-manylinux_2_17
module load "$SINGULARITY_MODULE"

mkdir -p "${LOG_DIR}/locks"
lock="${LOG_DIR}/locks/${subject}.lock"
mkdir "$lock"
trap 'rmdir "$lock"' EXIT
uv run --offline --no-sync efny-imaging start-container \
    --stage fmriprep --dataset "$dataset" --subject "$subject" \
    --config "$config" --project-root "$project_root"
mkdir -p "$OUTPUT_DIR" "$WORK_DIR" "$TEMP_DIR" "$FREESURFER_DIR"

# Do not inherit proxy injection into an offline compute-node container.
while IFS= read -r variable; do
    if [[ "${variable,,}" == *proxy* ]]; then unset "$variable"; fi
done < <(compgen -e)
export SINGULARITYENV_TEMPLATEFLOW_HOME=/templateflow SINGULARITYENV_SUBJECTS_DIR=/freesurfer
export SINGULARITYENV_TMPDIR=/tmp SINGULARITYENV_OMP_NUM_THREADS=1
export SINGULARITYENV_OPENBLAS_NUM_THREADS=1 SINGULARITYENV_MKL_NUM_THREADS=1 SINGULARITYENV_NUMEXPR_NUM_THREADS=1
tool_version=$(singularity run --cleanenv "$IMAGE" --version)

printf '%q ' "${command[@]}"
printf '\n'
"${command[@]}"
uv run --offline --no-sync efny-imaging finish-container \
    --stage fmriprep --dataset "$dataset" --subject "$subject" \
    --config "$config" --project-root "$project_root" --tool-version "$tool_version" \
    --container-command "${command[@]}"
