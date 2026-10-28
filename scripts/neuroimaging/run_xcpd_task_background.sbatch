#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH -p q_fat_c

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$(dirname "$(realpath "$0")")/../..}"
dataset="${1:?Dataset required}"
subject="${2:?Subject required}"
config="${3:-configs/neuroimaging_stc.json}"
project_root="${4:-$PWD}"
task="${5:?Task required}"
cpus="${SLURM_CPUS_PER_TASK:-1}"
[[ "$cpus" == 1 ]] || { echo "Task XCP-D requires one CPU" >&2; exit 2; }

# Read shared paths and configured values; regression, filtering and censoring are explicit below.
shell_values=$(uv run --offline --no-sync efny-imaging shell-config \
    --stage xcpd --scope task --task "$task" --dataset "$dataset" --subject "$subject" \
    --config "$config" --project-root "$project_root")
eval "$shell_values"

atlas_options=()
# Bash 4.2 treats empty array expansion as unset under nounset.
for bind in "${ATLAS_BINDS[@]+"${ATLAS_BINDS[@]}"}"; do atlas_options+=(-B "$bind"); done
atlas_datasets=(--datasets custom=/custom_confounds "${ATLAS_DATASETS[@]+"${ATLAS_DATASETS[@]}"}")

command=(
    singularity run --cleanenv
    -B "${FMRIPREP_DIR}:/fmriprep:ro"
    -B "${CUSTOM_CONFOUNDS_DIR}:/custom_confounds:ro"
    -B "${CONFOUNDS_CONFIG}:/task_confounds.yml:ro"
    -B "${BIDS_FILTER}:/bids_filter.json:ro"
    -B "${OUTPUT_DIR}:/output:rw"
    -B "${WORK_DIR}:/wd:rw"
    -B "${TEMP_DIR}:/tmp:rw"
    -B "${FS_LICENSE}:/fs_license/license.txt:ro"
    -B "${FREESURFER_DIR}:/freesurfer:ro"
    -B "${TEMPLATEFLOW}:/templateflow:ro"
    "${atlas_options[@]+"${atlas_options[@]}"}"
    "$IMAGE"
    /fmriprep /output participant
    --participant-label "${subject#sub-}"
    --input-type fmriprep
    --mode none
    --task-id "$task"
    --bids-filter-file /bids_filter.json
    --fs-license-file /fs_license/license.txt
    -w /wd
    --nprocs "$cpus"
    --omp-nthreads 1
    --nuisance-regressors /task_confounds.yml
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
    "${atlas_datasets[@]+"${atlas_datasets[@]}"}"
    --output-layout bids
    --notrack
    --random-seed "$XCPD_RANDOM_SEED"
    --stop-on-first-crash
)

if [[ "${6:-}" == --dry-run ]]; then
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
    --stage xcpd --scope task --task "$task" --dataset "$dataset" --subject "$subject" \
    --config "$config" --project-root "$project_root"
mkdir -p "$OUTPUT_DIR" "$WORK_DIR" "$TEMP_DIR"

# Preserve the reference compute-node proxy inside the clean container environment.
proxy_url="http://10.11.100.5:3128"
export http_proxy="$proxy_url" HTTP_PROXY="$proxy_url"
export https_proxy="$proxy_url" HTTPS_PROXY="$proxy_url"
export ftp_proxy="$proxy_url" FTP_PROXY="$proxy_url"
export all_proxy="$proxy_url" ALL_PROXY="$proxy_url"
export SINGULARITYENV_http_proxy="$proxy_url" SINGULARITYENV_HTTP_PROXY="$proxy_url"
export SINGULARITYENV_https_proxy="$proxy_url" SINGULARITYENV_HTTPS_PROXY="$proxy_url"
export SINGULARITYENV_ftp_proxy="$proxy_url" SINGULARITYENV_FTP_PROXY="$proxy_url"
export SINGULARITYENV_all_proxy="$proxy_url" SINGULARITYENV_ALL_PROXY="$proxy_url"
export SINGULARITYENV_TEMPLATEFLOW_HOME=/templateflow SINGULARITYENV_SUBJECTS_DIR=/freesurfer
export SINGULARITYENV_TMPDIR=/tmp SINGULARITYENV_OMP_NUM_THREADS=1
export SINGULARITYENV_OPENBLAS_NUM_THREADS=1 SINGULARITYENV_MKL_NUM_THREADS=1 SINGULARITYENV_NUMEXPR_NUM_THREADS=1
# Version startup imports TemplateFlow, so it needs the same mounts as processing.
tool_version=$("${command[@]}" --version)

printf '%q ' "${command[@]}"
printf '\n'
"${command[@]}"
uv run --offline --no-sync efny-imaging finish-container \
    --stage xcpd --scope task --task "$task" --dataset "$dataset" --subject "$subject" \
    --config "$config" --project-root "$project_root" --tool-version "$tool_version" \
    --container-command "${command[@]}"
