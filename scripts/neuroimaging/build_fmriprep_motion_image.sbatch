#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=3
#SBATCH -p q_fat_c

set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"
module load singularity/3.7.0
image="/ibmgpfs/cuizaixu_lab/xuhaoshu/packages/singularity/fmriprep-25.2.7.simg"
partial="${image}.building-${SLURM_JOB_ID}"
build_dir="/ibmgpfs/cuizaixu_lab/xuhaoshu/packages/singularity/build_fmriprep_25_2_7/${SLURM_JOB_ID}"
[[ ! -e "$image" && ! -e "$partial" ]] || { echo 'Review the existing image before rebuilding.' >&2; exit 2; }
mkdir -p "${build_dir}/tmp" "${build_dir}/cache" "${build_dir}/bin"
export SINGULARITY_TMPDIR="${build_dir}/tmp" SINGULARITY_CACHEDIR="${build_dir}/cache"
export GOMAXPROCS="${SLURM_CPUS_PER_TASK}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
proxy_url="http://10.11.100.5:3128"
export http_proxy="$proxy_url" HTTP_PROXY="$proxy_url" https_proxy="$proxy_url" HTTPS_PROXY="$proxy_url"
export ftp_proxy="$proxy_url" FTP_PROXY="$proxy_url" all_proxy="$proxy_url" ALL_PROXY="$proxy_url"

# Singularity 3.7 has no per-build mksquashfs thread flag; constrain its PATH-resolved packer.
export MOTION_BUILD_MKSQUASHFS
MOTION_BUILD_MKSQUASHFS=$(command -v mksquashfs)
cat > "${build_dir}/bin/mksquashfs" <<'SH'
#!/usr/bin/env bash
exec "$MOTION_BUILD_MKSQUASHFS" "$@" -processors "$SLURM_CPUS_PER_TASK"
SH
chmod u+x "${build_dir}/bin/mksquashfs"
export PATH="${build_dir}/bin:$PATH"
printf 'Code: %s\nSource: docker://nipreps/fmriprep:25.2.7\nTarget: %s\n' "$(git rev-parse HEAD)" "$image"
singularity --version
singularity build "$partial" docker://nipreps/fmriprep:25.2.7
singularity exec --cleanenv "$partial" python - <<'PY'
import json
import sys
from importlib.metadata import version
from fmriprep import __version__
from fmriprep.interfaces.confounds import FSLMotionParams, FramewiseDisplacement
from niworkflows.interfaces.confounds import ExpandModel, spike_regressors
assert __version__.split('+')[0] == '25.2.7', __version__
print(json.dumps(dict(fmriprep=__version__, python=sys.version,
    nipype=version('nipype'), niworkflows=version('niworkflows'),
    interfaces=[cls.__name__ for cls in (FSLMotionParams, FramewiseDisplacement, ExpandModel)]), indent=2))
PY
[[ ! -e "$image" ]] || { echo 'Target appeared during build; refusing to replace it.' >&2; exit 2; }
mv -T -- "$partial" "$image"
printf 'Published validated motion image: %s\n' "$image"
