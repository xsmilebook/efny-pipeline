# MRI series-folder inventory

`export_series_folders.py` lists only the sequence folders visible directly inside each scanner Study directory (`subject/MRIdata/*/*/sequence_folder`). It performs no file inspection, DICOM reading, or BIDS inference.

It writes two complementary files:

- `series_folders.jsonl`: primary GPT input; one complete JSON object per subject.
- `series_folders.csv`: one row per sequence folder, for spreadsheet QA.

The output omits original subject folder names and intermediate paths because scanner export folders can contain personal names. Study directories are represented as `scan_01`, `scan_02`, and so on.

## Run

```powershell
python .\scripts\neuroimaging\export_series_folders.py "Z:\xuhaoshu\20260909_bp_DICOM"
```

Outputs are written to:

- `outputs/logs/neuroimaging/series_folder_inventory/series_folders.jsonl`
- `outputs/tables/neuroimaging/series_folder_inventory/series_folders.csv`

## Output meaning

Each JSONL subject object contains:

- `subject_id`: compact ID parsed from the source folder, such as `THU_482`.
- `scan_groups`: anonymized scanner Study directories.
- `sequence_folders`: the literal folder names visible at the level shown in the scanner export.

The inventory deliberately does not decide whether a folder is raw, derived, repeated, interrupted, or BIDS-compatible.

## Suggested GPT prompt

Upload `series_folders.jsonl` and ask:

> This file lists the sequence-folder names under each subject's scanner Study directory. Summarize which sequences each subject has, group obvious folder-name families such as localizer, fieldmap/reverse-PE, BOLD rest/task, diffusion, T1 and T2, and compare missing, additional, or repeated sequence-folder names. Separate literal observations from hypotheses and do not infer acquisition parameters absent from folder names.
