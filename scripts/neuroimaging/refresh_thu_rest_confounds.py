"""Audit corrected THU rest confounds, then replace inputs and restart downstream analysis."""

import argparse
import csv
import json
import os
import re
import shlex
import shutil
import subprocess
import tarfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import nibabel as nib
import numpy as np

from imaging.config import load_config, module_path
from imaging.pipeline import assert_completed, input_scans
from imaging.rest import derivative_path, write_csv


def read_confounds(path: Path) -> tuple[list[str], list[list[str]]]:
    """Read the complete table without coercing missing values or changing volume order."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        table = list(csv.reader(stream, delimiter="\t"))
    columns, rows = table[0], table[1:]
    assert len(columns) == len(set(columns)) and all(len(row) == len(columns) for row in rows), path
    return columns, rows


def audit_run(config: dict, scan: dict, source_root: Path) -> dict:
    """Require aligned volumes, unchanged non-motion confounds and consistent corrected motion/FD."""
    target = derivative_path(config, scan, "fmriprep", "desc-confounds_timeseries.tsv")
    source = source_root / scan["subject"] / scan["func_dir"] / target.name
    columns, old = read_confounds(target)
    new_columns, new = read_confounds(source)
    old_outliers = [name for name in columns if name.startswith("motion_outlier")]
    new_outliers = [name for name in new_columns if name.startswith("motion_outlier")]
    assert all(re.fullmatch(r"motion_outlier\d+", name) for name in old_outliers + new_outliers), source
    assert [name for name in columns if name not in old_outliers] == [
        name for name in new_columns if name not in new_outliers], f"Non-outlier confound columns differ: {source}"
    frames = nib.load(scan["source_bold"]).shape[3]
    cifti = derivative_path(config, scan, "fmriprep", "space-fsLR_den-91k_bold.dtseries.nii")
    assert len(old) == len(new) == frames == nib.load(cifti).header.get_axis(0).size, scan["scan_id"]
    motion = [f"{kind}_{axis}" for kind in ("rot", "trans") for axis in "xyz"]
    allowed = {"framewise_displacement", *old_outliers, *new_outliers}
    for name in motion:
        allowed.update((name, name + "_derivative1", name + "_power2", name + "_derivative1_power2"))
    new_positions = {name: index for index, name in enumerate(new_columns)}
    changed = [name for index, name in enumerate(columns) if name not in new_positions or
               any(a[index] != b[new_positions[name]] for a, b in zip(old, new))]
    changed.extend(name for name in new_columns if name not in columns)
    assert set(changed) <= allowed, f"Non-motion confounds changed: {source}: {set(changed) - allowed}"
    old_fd_index = columns.index("framewise_displacement")
    columns = new_columns
    values = np.array([[row[columns.index(name)] for name in motion] for row in new], dtype=float)
    assert np.isfinite(values).all(), source
    fd_index = columns.index("framewise_displacement")
    assert new[0][fd_index] in ("n/a", "NaN", "nan", ""), f"First FD must be undefined: {source}"
    fd = np.array([row[fd_index] for row in new[1:]], dtype=float)
    assert np.isfinite(fd).all() and (fd >= 0).all(), source
    delta = np.diff(values, axis=0)
    expected_fd = np.abs(delta[:, 3:]).sum(axis=1) + 50 * np.abs(delta[:, :3]).sum(axis=1)
    np.testing.assert_allclose(fd, expected_fd, rtol=1e-7, atol=1e-9, err_msg=str(source))
    for index, name in enumerate(motion):
        for suffix, expected in (("_derivative1", delta[:, index]),
                                 ("_power2", values[1:, index] ** 2),
                                 ("_derivative1_power2", delta[:, index] ** 2)):
            observed = np.array([row[columns.index(name + suffix)] for row in new[1:]], dtype=float)
            np.testing.assert_allclose(observed, expected, rtol=1e-7, atol=1e-9, err_msg=f"{source}: {name}{suffix}")
    metadata = json.loads(source.with_suffix(".json").read_text())
    assert metadata["framewise_displacement"]["Units"] == "mm", source
    assert all(metadata[name]["Units"] == ("rad" if name.startswith("rot") else "mm") for name in motion), source
    # Corrected FD can legitimately add/remove spike columns; verify the documented rule.
    dvars = np.array([np.nan if row[columns.index("std_dvars")] in ("n/a", "NaN", "nan", "")
                      else float(row[columns.index("std_dvars")]) for row in new])
    spikes = np.array([[float(row[columns.index(name)]) for name in new_outliers] for row in new])
    assert np.isin(spikes, [0, 1]).all() and (spikes.sum(axis=0) == 1).all(), source
    assert (spikes.sum(axis=1) <= 1).all(), source
    expected_spikes = (np.r_[np.nan, fd] > 0.5) | (dvars > 1.5)
    assert np.array_equal(spikes.any(axis=1), expected_spikes), f"Incorrect motion outlier flags: {source}"
    assert all(metadata[name]["Description"] == "FD > 0.5 mm or standardized DVARS > 1.5." for name in new_outliers), source
    old_fd = np.array([row[old_fd_index] for row in old[1:]], dtype=float)
    return dict(subject=scan["subject"], scan_id=scan["scan_id"], frames=frames,
                changed_columns=";".join(changed), old_mean_fd_mm=float(old_fd.mean()),
                corrected_mean_fd_mm=float(fd.mean()), old_motion_outliers=len(old_outliers),
                corrected_motion_outliers=len(new_outliers), source=str(source), target=str(target),
                source_size=source.stat().st_size, source_mtime_ns=source.stat().st_mtime_ns,
                source_json_size=source.with_suffix(".json").stat().st_size,
                source_json_mtime_ns=source.with_suffix(".json").stat().st_mtime_ns)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Replace confounds, delete old downstream data, and resubmit.")
    args = parser.parse_args()
    config_path = Path("configs/neuroimaging_stc.json").resolve()
    config = load_config(config_path, "THU")
    assert config["scope"] == "rest" and not config["fmriprep"]["ignore"]
    root = Path(config["project_root"]).resolve()
    assert root == Path.cwd().resolve(), "Run from the configured cluster project root"
    scans = input_scans(config)
    subjects = sorted({scan["subject"] for scan in scans})
    fmriprep_logs = module_path(config, "fmriprep", "logs")
    assert subjects == (fmriprep_logs / "reference_subjects_success.txt").read_text().splitlines()
    expected = {Path(scan["subject"]) / scan["func_dir"] / (scan["scan_id"] + "_desc-confounds_timeseries.tsv") for scan in scans}
    assert {path.relative_to(args.source) for path in args.source.glob("sub-*/func/*confounds*.tsv")} == expected
    assert {path.relative_to(args.source).with_suffix(".tsv") for path in args.source.glob("sub-*/func/*confounds*.json")} == expected
    for subject in subjects:
        assert_completed(config, "fmriprep", subject, scans)
    for stage in ("fmriprep", "xcpd", "head_motion", "rest_fc"):
        assert not list((module_path(config, stage, "logs") / "locks").glob("*")), f"Active {stage} locks"
    active = subprocess.check_output(["squeue", "--noheader", "--user", os.environ["USER"], "--format=%i|%j"], text=True)
    assert not any(name in active for name in ("run_xcpd", "run_head_motion", "run_rest_fc", "efny_xcpd", "efny_head_motion", "efny_rest_fc")), active
    job = os.environ["SLURM_JOB_ID"]
    logs = fmriprep_logs / f"confounds_refresh_{job}"
    logs.mkdir()
    receipt = dict(job_id=job, mode="apply" if args.apply else "audit", source=str(args.source),
                   started_at_utc=datetime.now(timezone.utc).isoformat(), subjects=len(subjects), runs=len(scans),
                   code_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                   worktree_dirty=bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
                   command=["python", *os.sys.argv], resolved_config=config, numpy_version=np.__version__,
                   nibabel_version=nib.__version__, fmriprep_was_rerun=False)
    record = logs / "refresh.json"
    record.write_text(json.dumps(receipt, indent=2) + "\n")
    rows = []
    for index, scan in enumerate(scans):
        rows.append(audit_run(config, scan, args.source))
        if (index + 1) % 100 == 0:
            print(f"Audited {index + 1}/{len(scans)} runs", flush=True)
    write_csv(logs / "confounds_audit.csv", rows)
    receipt.update(audit_completed_at_utc=datetime.now(timezone.utc).isoformat(),
                   changed_runs=sum(bool(row["changed_columns"]) for row in rows))
    record.write_text(json.dumps(receipt, indent=2) + "\n")
    if not args.apply:
        print(json.dumps(receipt, indent=2), flush=True)
        return

    # Back up the replaced small inputs and original execution records before any mutation.
    with tarfile.open(logs / "original_confounds_and_records.tar.gz", "w:gz", compresslevel=1) as archive:
        for row in rows:
            for path in (Path(row["target"]), Path(row["target"]).with_suffix(".json")):
                assert not path.is_symlink() and path.resolve().is_relative_to(root), path
                archive.add(path, arcname=str(path.relative_to(root)), recursive=False)
        for subject in subjects:
            path = fmriprep_logs / "completed" / f"{subject}.json"
            archive.add(path, arcname=str(path.relative_to(root)), recursive=False)
    for row in rows:
        for suffix, size_key, time_key in ((".tsv", "source_size", "source_mtime_ns"),
                                          (".json", "source_json_size", "source_json_mtime_ns")):
            source, target = Path(row["source"]).with_suffix(suffix), Path(row["target"]).with_suffix(suffix)
            stat = source.stat()
            assert (stat.st_size, stat.st_mtime_ns) == (row[size_key], row[time_key]), f"Source changed during audit: {source}"
            temporary = target.with_name(target.name + f".replacement-{job}")
            shutil.copyfile(source, temporary)
            os.replace(temporary, target)
    replacement = dict(replaced_at_utc=datetime.now(timezone.utc).isoformat(), source_root=str(args.source),
                       audit_record=str(record), job_id=job, reason="User-supplied correction of MCFLIRT motion confounds")
    for subject in subjects:
        path = fmriprep_logs / "completed" / f"{subject}.json"
        marker = json.loads(path.read_text())
        marker["confounds_override"] = replacement
        path.write_text(json.dumps(marker, indent=2) + "\n")
    receipt.update(confounds_override=replacement, replaced_files=2 * len(rows))
    record.write_text(json.dumps(receipt, indent=2) + "\n")

    # Archive audit history and small tables; old denoised images, caches and FC are discarded.
    for stage in ("xcpd", "head_motion", "rest_fc"):
        previous = module_path(config, stage, "logs")
        previous.rename(logs / f"previous_{stage}_logs")
        previous.mkdir()
    for stage in ("head_motion", "rest_fc"):
        previous = module_path(config, stage, "tables")
        previous.rename(logs / f"previous_{stage}_tables")
    xcpd_output = module_path(config, "xcpd", "interim")
    cleanup_roots = [xcpd_output, xcpd_output.parent / "work", module_path(config, "xcpd", "temp"),
                     module_path(config, "rest_fc", "processed")]
    targets = []
    for path in cleanup_roots:
        assert not path.is_symlink() and path.resolve().is_relative_to(root) and path.resolve() != root, path
        assert "no_slicetiming" not in path.parts and "task" not in path.parts, path
        targets.extend(path.iterdir())
    receipt.update(cleanup_roots=list(map(str, cleanup_roots)), deletion_targets=list(map(str, targets)))
    record.write_text(json.dumps(receipt, indent=2) + "\n")

    def remove(target: Path) -> str:
        """Delete one enumerated child without following symlinks or crossing mounted filesystems."""
        assert target.parent in cleanup_roots and target.parent.resolve().is_relative_to(root), target
        subprocess.run(["rm", "--one-file-system", "-rf", "--", str(target)], check=True)
        assert not target.exists() and not target.is_symlink(), target
        return str(target)

    with (logs / "removed.jsonl").open("w") as stream:
        with ThreadPoolExecutor(max_workers=int(os.environ["SLURM_CPUS_PER_TASK"])) as pool:
            for removed in pool.map(remove, targets):
                stream.write(json.dumps(dict(removed=removed)) + "\n")
                stream.flush()
    assert all(not list(path.iterdir()) for path in cleanup_roots), "Cleanup incomplete"
    receipt.update(cleanup_completed_at_utc=datetime.now(timezone.utc).isoformat(), removed_count=len(targets))
    record.write_text(json.dumps(receipt, indent=2) + "\n")
    print("Replacement and downstream cleanup complete; submitting the pilot", flush=True)
    xcpd_logs = module_path(config, "xcpd", "logs")
    pilot = subjects[0]
    command = ["sbatch", "--parsable", "--chdir", str(root), "--partition", config["slurm"]["partition"],
               "--cpus-per-task", str(config["slurm"]["xcpd_cpus"]),
               "--output", str(xcpd_logs / f"{pilot}_%j.out"), "--error", str(xcpd_logs / f"{pilot}_%j.err"),
               str(root / "scripts/neuroimaging/run_xcpd.sbatch"), "THU", pilot, str(config_path)]
    pilot_job = subprocess.check_output(command, text=True).strip().split(";")[0]
    receipt.update(pilot_subject=pilot, pilot_job_id=pilot_job, pilot_command=shlex.join(command))
    record.write_text(json.dumps(receipt, indent=2) + "\n")
    controller = ["sbatch", "--parsable", "--chdir", str(root), "--partition", config["slurm"]["partition"],
                  "--cpus-per-task", "1", "--dependency", f"afterok:{pilot_job}", "--kill-on-invalid-dep=yes",
                  "--job-name", "efny_xcpd_refresh_batch", "--output", str(xcpd_logs / "refresh_batch_%j.out"),
                  "--error", str(xcpd_logs / "refresh_batch_%j.err"),
                  str(root / "scripts/neuroimaging/submit_xcpd_after_pilot.sbatch"), "THU", pilot, "keep-scope"]
    controller_job = subprocess.check_output(controller, text=True).strip().split(";")[0]
    receipt.update(batch_controller_job_id=controller_job, batch_controller_command=shlex.join(controller),
                   completed_at_utc=datetime.now(timezone.utc).isoformat())
    record.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2), flush=True)


if __name__ == "__main__":
    main()
