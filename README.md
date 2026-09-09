# MRI series-folder inventory

`export_series_folders.py` inventories the folder structure under a root whose immediate children are subject folders. It performs no DICOM/BIDS classification and does not read DICOM headers.

It writes two complementary files:

- `folder_inventory.jsonl`: primary GPT input; one complete JSON object per subject.
- `series_folders.csv`: one row per file-bearing folder under `MRIdata`, for spreadsheet QA.

The default output omits original subject folder names and intermediate paths because scanner export folders can contain personal names. Intermediate MRI containers are represented as `scan_01`, `scan_02`, and so on.

## Run

```powershell
python .\scripts\neuroimaging\export_series_folders.py "Z:\xuhaoshu\20260909_bp_DICOM"
```

Outputs are written to:

- `outputs/logs/neuroimaging/series_folder_inventory/folder_inventory.jsonl`
- `outputs/tables/neuroimaging/series_folder_inventory/series_folders.csv`

For internal traceability only, add `--include-source-paths`. Review that output before sharing it because paths can contain identifying information.

## Output meaning

Each JSONL subject object contains:

- `subject_id`: compact ID parsed from the source folder, such as `THU_482`.
- `direct_subfolders`: folders directly under the subject, including descendant folder/file counts and extension counts.
- `scan_groups`: anonymized groups of MRI series folders that share the same source parent.
- `series_folder`, `file_count`, and `extensions`: literal folder facts used for later sequence and conflict analysis.

The inventory deliberately does not decide whether a folder is raw, derived, repeated, interrupted, or BIDS-compatible. Those decisions should be made in a separate step using the folder facts, protocol documentation, and—when needed—DICOM headers or dcm2niix JSON sidecars.

## Suggested GPT prompt

Upload `folder_inventory.jsonl` and ask:

> This file is a folder-level MRI inventory with one JSON object per subject. First summarize, without assuming BIDS correctness, which series folders each subject has. Compare subjects with similar acquisition patterns and flag only observable differences: empty MRIdata, different scan-group counts, missing or additional folder names, repeated base names, and unusually small file counts. Separate literal observations from hypotheses. Do not infer acquisition parameters that are absent from this inventory. Then list which cases require DICOM-header or dcm2niix JSON inspection before DICOM2BIDS mapping.
