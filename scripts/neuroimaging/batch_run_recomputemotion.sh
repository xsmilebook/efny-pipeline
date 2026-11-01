#!/usr/bin/env bash
# Task adaptation of the user-supplied batch_run_recomputemotion.sh.
# Submit an explicit frozen subject list; retain every successful sbatch receipt.
set -euo pipefail
cd "$(dirname "$(realpath "$0")")/../.."
old="${1:?THU task fMRIPrep directory required}"
out="${2:?Corrected confounds staging directory required}"
subjects="${3:?Frozen subject list required}"
logs="${4:?Submission log directory required}"
mkdir -p "$logs"
receipt="${logs}/motion_submitted.tsv"
[[ ! -e "$receipt" ]] || { echo 'Submission receipts already exist; review before retrying.' >&2; exit 2; }
printf 'subject\tjob_id\n' > "$receipt"
while IFS= read -r subject; do
    [[ "$subject" == sub-THU* && "$subject" != *$'\r'* ]] || exit 2
    job=$(sbatch --parsable --chdir "$PWD" --partition=q_fat_c --cpus-per-task=3 \
        --output "${logs}/${subject}_%j.out" --error "${logs}/${subject}_%j.err" \
        scripts/neuroimaging/recompute_motion_25_2_7.sh "$subject" "$out" "$old")
    printf '%s\t%s\n' "$subject" "${job%%;*}" >> "$receipt"
done < "$subjects"
cat "$receipt"
