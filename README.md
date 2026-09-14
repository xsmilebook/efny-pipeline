# MRI series-folder inventory

`export_series_folders.py` recursively searches below each subject's `MRIdata`. It exports a directory when one or more of its immediate child-folder names match this cohort's sequence conventions: `EP2D_`, `LOCALIZER`, `PHOENIXZIPREPORT`, `SMS*_BOLD_`, `SMS*_DIFF_`, `T1_`, or `T2_`. For each exported directory, it records the path relative to `MRIdata` and only the child folders matching these prefixes. It performs no file inspection, DICOM reading, scan/session inference, or BIDS inference.

This detection is independent of depth, so both `MRIdata/container/sequence` and `MRIdata/wrapper/container/sequence` layouts are supported. A directory containing only unfamiliar sequence names will not be exported until its prefix is added to `SEQUENCE_FOLDER_PATTERN`.

It writes two complementary files:

- `series_folders.jsonl`: primary GPT input; one complete JSON object per subject.
- `series_folders.csv`: one row per sequence folder, for spreadsheet QA.

The output replaces the original subject-folder name with the compact subject ID, but preserves the path below `MRIdata` as `relative_path`. These relative paths may contain scanner-export names and should be reviewed before sharing outside the project.

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
- `sequence_containers`: directories that directly contain one or more matching sequence folders.
- `relative_path`: the container path relative to the subject's `MRIdata`; `.` means `MRIdata` itself.
- `sequence_folders`: only the literal child-folder names matching the configured prefixes.

The inventory deliberately does not decide whether a folder is raw, derived, repeated, interrupted, or BIDS-compatible.

## Suggested GPT prompt

Upload `series_folders.jsonl` and ask:

> This file lists the sequence-folder names under each subject's scanner Study directory. Summarize which sequences each subject has, group obvious folder-name families such as localizer, fieldmap/reverse-PE, BOLD rest/task, diffusion, T1 and T2, and compare missing, additional, or repeated sequence-folder names. Separate literal observations from hypotheses and do not infer acquisition parameters absent from folder names.

## Checked DICOM to BIDS conversion

`dicom2bids_checked.m` is the one-session conversion entry for one participant.
It discovers scan containers below `MRIdata`, resolves supported BOLD rescans
before conversion, excludes derived DWI folders, pairs complete AP/PA
fieldmaps, and assigns fieldmap runs by acquisition time. It refuses existing
subject output directories instead of overwriting them.

Repeated Prescan Normalize T1, T2, main DWI, and DWI B0 series are resolved by
keeping the series with the most DICOM files and then the latest acquisition
time. A repeated rest run prefers the latest 180-volume candidate. If no
180-volume candidate exists, the latest available run is retained with a
warning. When multiple event CSV files match one retained task, the file with
the most data rows is retained; filename timestamps select the latest file only
when the largest row count is tied. PsychoPy task names are recognized only as
underscore-delimited `_SST_`, `_nback_`, or `_switch_` filename tokens.
Timestamps with or without milliseconds are accepted.

Within one scan container, fieldmaps with the largest DICOM file count are
treated as complete. If only the regular or `_TASK` AP/PA pair is complete,
that pair is linked to every retained BOLD run in the scan. If both are
complete, the regular pair is linked only to rest BOLD and the `_TASK` pair
only to task BOLD. Incomplete fieldmaps are omitted with a warning.

DWI B0 selection is restricted to the source scan containing the retained main
DWI. Conversion stops if that scan has no DWI B0 series. This rule governs the
DWI B0 `IntendedFor` link to DWI and does not change functional fieldmap links
to BOLD.

The converter creates only BIDS modality directories that receive selected
data; it does not emit empty modality directories, selection statistics, or
event-selection console messages.

The source folder name `THU_YYYYMMDD_ID_*` is converted directly to
`sub-THUYYYYMMDDXXXX`; three-digit IDs receive a leading zero, four-digit IDs
are unchanged, and all name text after the numeric ID is excluded.

Auxiliary and unsupported folders are classified by name and skipped before
DICOM inspection. Empty `LOCALIZER*` or `PHOENIXZIPREPORT*` directories do not
stop subject conversion.

Selected series are passed to `dcm2niix` with `-i y`; checks on this cohort
confirmed that it does not exclude the selected Prescan Normalize T1 or DWI B0
series. On Windows, a selected series containing a DICOM path of 260 characters
or more is exposed to `dcm2niix` through a unique short temporary directory
junction. If the source location does not support junctions, the series is
copied to a short local temporary directory with sequential file names. These
temporary inputs are isolated across parallel workers and removed when the
series conversion finishes or raises an error. A conversion failure skips only
that series with a warning. If one
direction of a functional fieldmap pair fails, both directions of that pair are
omitted. SST event CSV headers are preserved, and the required `bad` column is
matched case-insensitively after removing surrounding whitespace and a possible
byte order mark. All required PsychoPy component fields are resolved from their
original dotted headers, with the underscore form accepted for older exports.
Before event calculation, the task-specific required columns are checked as one
schema. A failure in event-file selection, schema validation, conversion, or
writing skips only that task's events with a warning and does not fail the
participant's converted imaging data.

The batch entry point uses the project-specific paths and worker count written
at the top of the script. Run it from MATLAB without arguments:

```matlab
addpath('D:\projects\efny-pipeline\scripts\neuroimaging');
run_dicom2bids_checked
```

Subjects run in parallel with errors isolated per subject. A failed subject
emits a warning while the remaining subjects continue.

The complete imaging and PsychoPy event conversion requires only
`dicom2bids_checked.m` and `run_dicom2bids_checked.m`. The runner adds its own
directory to the MATLAB path, so these two files can be copied together to a
different conversion environment after updating the project-specific paths.

The conversion does not use the inventory CSV as input.

## PsychoPy-only BIDS event replacement

`psychopy2bids_checked.m` builds a standalone BIDS events-only dataset for
replacing event files without retransferring imaging data. Call it with the raw
participant root, a dedicated output BIDS root, and the same source-folder list
used by the DICOM conversion:

```matlab
addpath('D:\projects\efny-pipeline\scripts\neuroimaging');
psychopy2bids_checked( ...
    'D:\Raw_trans', ...
    'D:\BIDS_transfer\BIDS_EVENTS', ...
    'D:\BIDS_transfer\raw\sublist.txt');
```

The output root contains the required `dataset_description.json`; each subject
directory contains only `func/*_events.tsv` and matching JSON sidecars. For each
SST, n-back, or switch task, multiple PsychoPy CSV files are resolved by keeping
the file with the most data rows and then the latest filename timestamp when
row counts tie. Existing output event files are overwritten, and the BIDS names
match the full converter so the generated subject directories can replace old
event files in the cluster dataset. When merging the replacement into the
cluster dataset, transfer the `sub-*` directories with overwrite enabled; do
not replace the cluster dataset's root `dataset_description.json` with the
minimal validation metadata from this replacement package.
