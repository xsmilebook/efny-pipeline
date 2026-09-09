#!/usr/bin/env python3
"""Export subject folders and MRI series-folder facts without BIDS inference."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def subject_id_from_folder(name: str) -> str:
    """Derive a compact subject code while omitting date and name initials."""
    match = re.match(
        r"(?P<center>[A-Za-z]+)[_-]\d{8}[_-](?P<number>\d+)(?:[_-].*)?$", name
    )
    if not match:
        raise ValueError(
            f"Subject folder does not match CENTER_YYYYMMDD_NUMBER_*: {name}"
        )
    return f"{match.group('center').upper()}_{match.group('number')}"


def extension_counts(filenames: list[str]) -> dict[str, int]:
    """Count file extensions, preserving extension-less files explicitly."""
    counts = Counter(Path(name).suffix.lower() or "[no_extension]" for name in filenames)
    return dict(sorted(counts.items()))


def scan_subject(subject_dir: Path, include_source_paths: bool) -> dict[str, Any]:
    """Collect direct-subfolder and file-bearing MRI-folder facts for one subject."""
    subject_id = subject_id_from_folder(subject_dir.name)
    direct_dirs = sorted((p for p in subject_dir.iterdir() if p.is_dir()), key=lambda p: p.name)
    direct_stats = {
        path.name: {"folder_count": 0, "file_count": 0, "extensions": Counter()}
        for path in direct_dirs
    }
    mri_series_by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def raise_walk_error(error: OSError) -> None:
        raise error

    for dirpath, dirnames, filenames in os.walk(subject_dir, onerror=raise_walk_error):
        folder = Path(dirpath)
        relative = folder.relative_to(subject_dir)
        if not relative.parts:
            continue

        direct_name = relative.parts[0]
        stats = direct_stats[direct_name]
        stats["folder_count"] += len(dirnames)
        stats["file_count"] += len(filenames)
        stats["extensions"].update(
            Path(name).suffix.lower() or "[no_extension]" for name in filenames
        )

        if direct_name.lower() != "mridata" or not filenames:
            continue

        parent_key = str(relative.parent)
        series = {
            "series_folder": folder.name,
            "file_count": len(filenames),
            "extensions": extension_counts(filenames),
        }
        if include_source_paths:
            series["relative_path"] = str(relative)
        mri_series_by_parent[parent_key].append(series)

    scan_groups = []
    for index, parent_key in enumerate(sorted(mri_series_by_parent), 1):
        series_folders = sorted(
            mri_series_by_parent[parent_key], key=lambda item: item["series_folder"]
        )
        group = {
            "scan_group": f"scan_{index:02d}",
            "series_folder_count": len(series_folders),
            "series_folders": series_folders,
        }
        if include_source_paths:
            group["source_parent"] = parent_key
        scan_groups.append(group)

    direct_subfolders = []
    for path in direct_dirs:
        stats = direct_stats[path.name]
        direct_subfolders.append(
            {
                "name": path.name,
                "descendant_folder_count": stats["folder_count"],
                "file_count": stats["file_count"],
                "extensions": dict(sorted(stats["extensions"].items())),
            }
        )

    return {
        "subject_id": subject_id,
        **({"source_subject_folder": subject_dir.name} if include_source_paths else {}),
        "direct_subfolders": direct_subfolders,
        "scan_group_count": len(scan_groups),
        "series_folder_count": sum(
            group["series_folder_count"] for group in scan_groups
        ),
        "scan_groups": scan_groups,
    }


def write_jsonl(subjects: list[dict[str, Any]], path: Path) -> None:
    """Write one complete subject object per line for chunkable LLM input."""
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for subject in subjects:
            json.dump(subject, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")


def write_csv(subjects: list[dict[str, Any]], path: Path) -> None:
    """Write one row per MRI series folder for spreadsheet inspection."""
    fields = [
        "subject_id",
        "scan_group",
        "series_folder",
        "file_count",
        "extensions",
        "relative_path",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for subject in subjects:
            for group in subject["scan_groups"]:
                for series in group["series_folders"]:
                    row = {
                        "subject_id": subject["subject_id"],
                        "scan_group": group["scan_group"],
                        **series,
                        "extensions": json.dumps(
                            series["extensions"], ensure_ascii=False, separators=(",", ":")
                        ),
                    }
                    writer.writerow(row)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root", type=Path, help="Root directory whose immediate children are subjects"
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("outputs"),
        help="Output root (default: outputs)",
    )
    parser.add_argument(
        "--include-source-paths",
        action="store_true",
        help="Include original folder names and paths; these may contain personal names",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(os.path.abspath(args.root))
    subject_dirs = sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name)
    subjects = []
    for index, subject_dir in enumerate(subject_dirs, 1):
        print(f"[{index}/{len(subject_dirs)}] {subject_dir.name}")
        subjects.append(scan_subject(subject_dir, args.include_source_paths))

    output_root = Path(os.path.abspath(args.output_root))
    json_dir = output_root / "logs" / "neuroimaging" / "series_folder_inventory"
    csv_dir = output_root / "tables" / "neuroimaging" / "series_folder_inventory"
    json_dir.mkdir(parents=True, exist_ok=True)
    csv_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(subjects, json_dir / "folder_inventory.jsonl")
    write_csv(subjects, csv_dir / "series_folders.csv")
    print(f"Wrote {len(subjects)} subjects")
    print(f"JSONL: {json_dir / 'folder_inventory.jsonl'}")
    print(f"CSV:   {csv_dir / 'series_folders.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
