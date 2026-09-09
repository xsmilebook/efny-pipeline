#!/usr/bin/env python3
"""List containers whose direct child folders match MRI sequence prefixes."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from pathlib import Path


SEQUENCE_FOLDER_PATTERN = re.compile(
    r"^(?:EP2D_|LOCALIZER|PHOENIXZIPREPORT|SMS.*_(?:BOLD|DIFF)_|T1_|T2_)",
    re.IGNORECASE,
)


def is_sequence_folder(name: str) -> bool:
    """Return whether a folder name matches this cohort's sequence conventions."""
    return SEQUENCE_FOLDER_PATTERN.match(name) is not None


def subject_id_from_folder(name: str) -> str:
    """Convert THU_YYYYMMDD_NUMBER_* to a compact subject identifier."""
    match = re.match(
        r"(?P<center>[A-Za-z]+)[_-]\d{8}[_-](?P<number>\d+)(?:[_-].*)?$", name
    )
    if not match:
        raise ValueError(f"Unexpected subject folder name: {name}")
    return f"{match.group('center').upper()}_{match.group('number')}"


def scan_subject(subject_dir: Path) -> dict:
    """List MRIdata-relative containers and their matching sequence folders."""
    mri_dir = subject_dir / "MRIdata"
    sequence_containers = []

    if mri_dir.is_dir():
        for dirpath, dirnames, _ in os.walk(mri_dir):
            dirnames.sort()
            matched_names = [name for name in dirnames if is_sequence_folder(name)]
            if matched_names:
                relative_path = Path(dirpath).relative_to(mri_dir).as_posix()
                sequence_containers.append(
                    {
                        "relative_path": relative_path or ".",
                        "sequence_folders": matched_names,
                    }
                )
                # Sequence directories contain DICOM files, which are irrelevant here.
                dirnames[:] = [name for name in dirnames if not is_sequence_folder(name)]

    return {
        "subject_id": subject_id_from_folder(subject_dir.name),
        "sequence_containers": sorted(
            sequence_containers, key=lambda item: item["relative_path"]
        ),
    }


def write_jsonl(subjects: list[dict], path: Path) -> None:
    """Write one compact subject record per line for GPT analysis."""
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for subject in subjects:
            json.dump(subject, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")


def write_csv(subjects: list[dict], path: Path) -> None:
    """Write one sequence-folder name per row for spreadsheet inspection."""
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["subject_id", "relative_path", "sequence_folder"])
        for subject in subjects:
            for container in subject["sequence_containers"]:
                for sequence_folder in container["sequence_folders"]:
                    writer.writerow(
                        [
                            subject["subject_id"],
                            container["relative_path"],
                            sequence_folder,
                        ]
                    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("outputs"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(os.path.abspath(args.root))
    subject_dirs = sorted((path for path in root.iterdir() if path.is_dir()))
    subjects = [scan_subject(subject_dir) for subject_dir in subject_dirs]

    output_root = Path(os.path.abspath(args.output_root))
    json_dir = output_root / "logs" / "neuroimaging" / "series_folder_inventory"
    csv_dir = output_root / "tables" / "neuroimaging" / "series_folder_inventory"
    json_dir.mkdir(parents=True, exist_ok=True)
    csv_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(subjects, json_dir / "series_folders.jsonl")
    write_csv(subjects, csv_dir / "series_folders.csv")

    sequence_count = sum(
        len(container["sequence_folders"])
        for subject in subjects
        for container in subject["sequence_containers"]
    )
    print(f"Subjects: {len(subjects)}")
    print(
        "Sequence containers: "
        f"{sum(len(s['sequence_containers']) for s in subjects)}"
    )
    print(f"Sequence folders: {sequence_count}")
    print(f"JSONL: {json_dir / 'series_folders.jsonl'}")
    print(f"CSV:   {csv_dir / 'series_folders.csv'}")


if __name__ == "__main__":
    main()
