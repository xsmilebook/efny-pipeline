"""Audit staged 25.2.7 task motion, replace confounds, and restart isolated task XCP-D."""

import argparse
import csv
import json
import os
import shlex
import shutil
import subprocess
import tarfile
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

from imaging.background import prepare_background
from imaging.config import load_config, module_path
from imaging.pipeline import assert_completed, input_scans
from imaging.rest import read_csv, write_csv
from scripts.neuroimaging.refresh_thu_rest_confounds import audit_run


def task_cleanup_targets(configs: list[dict]) -> tuple[list[Path], list[Path]]:
    """Enumerate only THU task-owned outputs/caches; reject root or child symlink escapes."""
    root = Path(configs[0]["project_root"]).resolve()
    owners = []
    for config in configs:
        assert config["dataset"] == "THU" and config["scope"] == "task"
        assert not config["fmriprep"]["ignore"]
        assert config["task"] in ("sst", "nback", "switch")
        output = module_path(config, "xcpd", "interim")
        owners.extend((output, output.parents[1] / "work_task_background" / config["task"],
                       module_path(config, "xcpd", "temp"),
                       module_path(config, "background_fc", "processed")))
    assert len(owners) == len(set(owners))
    targets = []
    for owner in owners:
        assert not owner.is_symlink() and owner.resolve().is_relative_to(root), owner
        assert owner.resolve() != root and owner.name in ("sst", "nback", "switch"), owner
        assert any(part in ("task_background", "work_task_background") for part in owner.parts), owner
        # Check ancestors too: a task directory may sit below a redirected module root.
        for parent in owner.parents:
            if parent == root:
                break
            assert not parent.is_symlink(), parent
        if owner.exists():
            for target in sorted(owner.iterdir()):
                assert not target.is_symlink() and target.resolve().parent == owner.resolve(), target
                targets.append(target)
    return owners, targets


def prepare_task(config_path: Path, task: str) -> None:
    """Re-audit one task after replacement so its prepared snapshot uses corrected 36P."""
    config = load_config(config_path, "THU", scope="task", task=task)
    prepare_background(config, input_scans(config), None)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-root", type=Path, required=True)
    parser.add_argument("--jobs", type=Path, required=True, help="Frozen subject/job_id TSV for successful recomputation.")
    parser.add_argument("--subjects", type=Path, help="Audit a small explicit pilot subset only.")
    parser.add_argument("--apply", action="store_true", help="After full audit, back up/replace, delete old task XCP-D, and resubmit.")
    args = parser.parse_args()
    assert not (args.apply and args.subjects), "Replacement requires the full original task cohort"
    config_path = Path("configs/neuroimaging_stc.json").resolve()
    config = load_config(config_path, "THU", scope="task")
    root = Path(config["project_root"]).resolve()
    assert root == Path.cwd().resolve() and not config["fmriprep"]["ignore"]
    logs = module_path(config, "fmriprep", "logs")
    refresh = args.refresh_root.resolve()
    assert refresh.parent == logs.resolve() and refresh.name.startswith("confounds_refresh_"), refresh
    if args.apply:
        assert not (refresh / "original_confounds_and_records.tar.gz").exists(), "A prior apply already started; review its receipt"
        assert not (refresh / "removed.jsonl").exists(), "Prior cleanup already started"
    source = refresh / "corrected_confounds"
    scans = input_scans(config)
    assert scans == read_csv(refresh / "input_scans_original.csv"), "Task identity/order changed during recomputation"
    full_subjects = sorted({scan["subject"] for scan in scans})
    subjects = args.subjects.read_text().splitlines() if args.subjects else full_subjects
    assert subjects and len(subjects) == len(set(subjects)) and set(subjects) <= set(full_subjects)
    selected = [scan for scan in scans if scan["subject"] in subjects]
    with args.jobs.open() as stream:
        jobs = list(csv.DictReader(stream, delimiter="\t"))
    assert len(jobs) == len(subjects) and {row["subject"] for row in jobs} == set(subjects)
    ids = [row["job_id"] for row in jobs]
    assert len(ids) == len(set(ids)) and all(job.isdigit() for job in ids)
    states = {}
    for start in range(0, len(ids), 250):
        output = subprocess.check_output(["sacct", "-X", "-j", ",".join(ids[start:start+250]),
                   "--format=JobID,State,ExitCode", "-n", "-P"], text=True)
        for line in output.splitlines():
            fields = line.split("|")
            states[fields[0]] = fields[1:3]
    assert set(states) == set(ids) and all(value == ["COMPLETED", "0:0"] for value in states.values()), states
    expected = {Path(scan["subject"]) / scan["func_dir"] / (scan["scan_id"] + "_desc-confounds_timeseries.tsv")
                for scan in selected}
    assert {p.relative_to(source) for p in source.glob("sub-*/func/*confounds*.tsv")} == expected
    assert {p.relative_to(source).with_suffix(".tsv") for p in source.glob("sub-*/func/*confounds*.json")} == expected
    for subject in subjects:
        assert_completed(config, "fmriprep", subject, scans)
        if args.apply:
            marker = json.loads((logs / "completed" / f"{subject}.json").read_text())
            assert "confounds_override" not in marker, "Review an existing task override before replacing it"
    workers = int(os.environ["SLURM_CPUS_PER_TASK"])
    job_id = os.environ["SLURM_JOB_ID"]
    label = "pilot" if args.subjects else "full"
    receipt_path = refresh / f"refresh_{label}_{job_id}.json"
    receipt = dict(started_at_utc=datetime.now(timezone.utc).isoformat(), job_id=job_id,
                   code_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                   tracked_worktree_dirty=bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
                   apply=args.apply, subjects=subjects, runs=len(selected), corrected_source=str(source),
                   motion_image=json.loads((refresh / "run.json").read_text())["image"],
                   recomputation_jobs=jobs, verified_states=states, workers=workers)
    assert not receipt["tracked_worktree_dirty"], "Commit code before applying the refresh"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    rows = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for index, row in enumerate(pool.map(partial(audit_run, config, source_root=source), selected), start=1):
            rows.append(row)
            if index % 100 == 0:
                print(f"Audited {index}/{len(selected)} corrected task runs", flush=True)
    write_csv(refresh / f"confounds_audit_{label}_{job_id}.csv", rows)
    receipt.update(audit_completed_at_utc=datetime.now(timezone.utc).isoformat(),
                   changed_runs=sum(bool(row["changed_columns"]) for row in rows))
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    if not args.apply:
        print(json.dumps(receipt, indent=2), flush=True)
        return

    configs = [load_config(config_path, "THU", scope="task", task=task) for task in ("sst", "nback", "switch")]
    owners, targets = task_cleanup_targets(configs)
    active = subprocess.check_output(["squeue", "-h", "-u", os.environ["USER"], "-o", "%i|%j|%o"], text=True)
    assert not any(name in active for name in ("run_fmriprep_task", "run_xcpd_task", "thu_background", "run_background_fc", "run_head_motion_task")), active
    assert not list((logs / "locks").glob("*")), "Active task preprocessing lock"
    old_job_ids = set()
    for task_config in configs:
        previous_logs = module_path(task_config, "xcpd", "logs")
        assert not list((previous_logs / "locks").glob("*")), previous_logs
        for path in (previous_logs / "completed").glob("*.json"):
            old_job_ids.add(json.loads(path.read_text())["job_id"])
    for start in range(0, len(old_job_ids), 250):
        chunk = sorted(old_job_ids)[start:start+250]
        output = subprocess.check_output(["sacct", "-X", "-j", ",".join(chunk), "--format=JobID,State,ExitCode", "-n", "-P"], text=True)
        states = [line.split("|") for line in output.splitlines()]
        assert {row[0] for row in states} == set(chunk) and all(row[1:3] == ["COMPLETED", "0:0"] for row in states), states
    receipt.update(cleanup_roots=list(map(str, owners)), deletion_targets=list(map(str, targets)),
                   previous_successful_job_ids=sorted(old_job_ids))
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    with tarfile.open(refresh / "original_confounds_and_records.tar.gz", "w:gz", compresslevel=1) as archive:
        for row in rows:
            for path in (Path(row["target"]), Path(row["target"]).with_suffix(".json")):
                assert not path.is_symlink() and path.resolve().is_relative_to(root), path
                archive.add(path, arcname=str(path.relative_to(root)), recursive=False)
        for subject in subjects:
            path = logs / "completed" / f"{subject}.json"
            archive.add(path, arcname=str(path.relative_to(root)), recursive=False)
    for row in rows:
        for suffix, size, mtime in ((".tsv", "source_size", "source_mtime_ns"),
                                    (".json", "source_json_size", "source_json_mtime_ns")):
            src, target = Path(row["source"]).with_suffix(suffix), Path(row["target"]).with_suffix(suffix)
            assert (src.stat().st_size, src.stat().st_mtime_ns) == (row[size], row[mtime]), src
            temporary = target.with_name(target.name + ".replacement-" + job_id)
            shutil.copyfile(src, temporary)
            os.replace(temporary, target)
    override = dict(replaced_at_utc=datetime.now(timezone.utc).isoformat(), source_root=str(source),
                    audit_record=str(receipt_path), job_id=job_id, motion_software="fMRIPrep 25.2.7",
                    reason="User-authorized MCFLIRT motion reconstruction correction for task confounds")
    for subject in subjects:
        path = logs / "completed" / f"{subject}.json"
        marker = json.loads(path.read_text())
        assert "confounds_override" not in marker, "Review a previous task override before replacing it"
        marker["confounds_override"] = override
        path.write_text(json.dumps(marker, indent=2) + "\n")
    receipt.update(confounds_override=override, replaced_files=2 * len(rows))
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

    # Retain complete logs and small tables; delete only owned task downstream products.
    for stage in ("xcpd", "head_motion", "background_fc"):
        for kind in ("logs", "tables"):
            previous = module_path(configs[0], stage, kind).parent
            assert not previous.is_symlink() and previous.resolve().is_relative_to(root)
            if previous.exists():
                previous.rename(refresh / f"previous_{stage}_{kind}")
                previous.mkdir()

    def remove(target: Path) -> str:
        """Remove an enumerated child without crossing filesystems or following a root symlink."""
        assert target.parent in owners and not target.is_symlink()
        assert target.resolve().parent == target.parent.resolve() and target.resolve().is_relative_to(root)
        subprocess.run(["rm", "--one-file-system", "-rf", "--", str(target)], check=True)
        assert not target.exists() and not target.is_symlink(), target
        return str(target)

    with (refresh / "removed.jsonl").open("x") as stream:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for removed in pool.map(remove, targets):
                stream.write(json.dumps(dict(removed=removed)) + "\n")
                stream.flush()
    assert all(not owner.exists() or not list(owner.iterdir()) for owner in owners)
    receipt.update(cleanup_completed_at_utc=datetime.now(timezone.utc).isoformat(), removed_count=len(targets))
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    with ProcessPoolExecutor(max_workers=min(workers, 3)) as pool:
        list(pool.map(partial(prepare_task, config_path), ("sst", "nback", "switch")))
    original_scope = json.loads((refresh / "original_background_scope.json").read_text())
    for task_config in configs:
        task = task_config["task"]
        current = (module_path(task_config, "xcpd", "logs") / "subjects_ready.txt").read_text().splitlines()
        assert current == original_scope[task]["subjects"], "Ready task cohort changed during motion refresh"
    new_logs = module_path(configs[0], "xcpd", "logs").parent
    registry = new_logs / ("run_motion_corrected_" + job_id + ".json")
    command = ["sbatch", "--parsable", "--partition=q_fat_c", "--cpus-per-task=1", "--chdir=" + str(root),
               "--job-name=thu_background_corrected_pilot", "--output=" + str(new_logs / "pilot_all_%j.out"),
               "--error=" + str(new_logs / "pilot_all_%j.err"),
               str(root / "scripts/neuroimaging/submit_task_background.sbatch"), "pilot", str(registry)]
    pilot_job = subprocess.check_output(command, text=True).strip().split(";")[0]
    receipt.update(prepared_at_utc=datetime.now(timezone.utc).isoformat(), new_registry=str(registry),
                   pilot_controller_job_id=pilot_job, pilot_controller_command=shlex.join(command))
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2), flush=True)


if __name__ == "__main__":
    main()
