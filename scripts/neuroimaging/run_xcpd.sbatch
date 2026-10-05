#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH -p q_fat_c

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$(dirname "$(realpath "$0")")/../..}"
dataset="${1:?Dataset required}"
subject="${2:?Subject required}"
config="${3:-configs/neuroimaging.json}"
project_root="${4:-$PWD}"
cpus="${SLURM_CPUS_PER_TASK:-1}"

# Read shared paths and configured values; regression, filtering and censoring are explicit below.
shell_values=$(uv run --offline --no-sync efny-imaging shell-config \
    --stage xcpd --dataset "$dataset" --subject "$subject" \
    --config "$config" --project-root "$project_root")
eval "$shell_values"

atlas_options=()
for bind in "${ATLAS_BINDS[@]}"; do atlas_options+=(-B "$bind"); done
atlas_datasets=()
if [[ "${#ATLAS_DATASETS[@]}" -gt 0 ]]; then
    atlas_datasets=(--datasets "${ATLAS_DATASETS[@]}")
fi

command=(
    singularity run --cleanenv
    -B "${FMRIPREP_DIR}:/fmriprep:ro"
    -B "${OUTPUT_DIR}:/output:rw"
    -B "${WORK_DIR}:/wd:rw"
    -B "${TEMP_DIR}:/tmp:rw"
    -B "${FS_LICENSE}:/fs_license/license.txt:ro"
    -B "${FREESURFER_DIR}:/freesurfer:ro"
    -B "${TEMPLATEFLOW}:/templateflow:ro"
    "${atlas_options[@]}"
    "$IMAGE"
    /fmriprep /output participant
    --participant-label "${subject#sub-}"
    --input-type fmriprep
    --mode none
    --task-id rest
    --fs-license-file /fs_license/license.txt
    -w /wd
    --nprocs "$cpus"
    --omp-nthreads 1
    --nuisance-regressors "$XCPD_NUISANCE_REGRESSORS"
    --dummy-scans "$XCPD_DUMMY_SCANS"
    --smoothing 0
    --despike n
    --file-format cifti
    --output-type censored
    --combine-runs n
    --warp-surfaces-native2std n
    --linc-qc n
    --abcc-qc n
    --min-coverage "$XCPD_MIN_COVERAGE"
    --create-matrices all
    --output-run-wise-correlations y
    --head-radius auto
    --bpf-order "$XCPD_BPF_ORDER"
    --lower-bpf "$XCPD_LOWER_BPF_HZ"
    --upper-bpf "$XCPD_UPPER_BPF_HZ"
    --motion-filter-type "$XCPD_MOTION_FILTER_TYPE"
    --band-stop-min "$XCPD_MOTION_FILTER_BPM"
    --fd-thresh 0
    --atlases "${ATLAS_NAMES[@]}"
    "${atlas_datasets[@]}"
    --output-layout bids
    --notrack
    --random-seed "$XCPD_RANDOM_SEED"
    --stop-on-first-crash
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
    --stage xcpd --dataset "$dataset" --subject "$subject" \
    --config "$config" --project-root "$project_root"
mkdir -p "$OUTPUT_DIR" "$WORK_DIR" "$TEMP_DIR"

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
    --stage xcpd --dataset "$dataset" --subject "$subject" \
    --config "$config" --project-root "$project_root" --tool-version "$tool_version" \
    --container-command "${command[@]}"
