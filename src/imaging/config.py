"""Resolve the shared neuroimaging configuration and module-owned paths."""

import json
import os
import shlex
from pathlib import Path


def load_config(path: Path, dataset: str, project_root: Path | None = None) -> dict:
    """Resolve THU/XY inputs without substituting another dataset's BIDS root."""
    config = json.loads(path.read_text(encoding="utf-8"))
    config["dataset"] = dataset
    config["project_root"] = str(project_root or config["project_root"])
    bids_dir = config["datasets"][dataset]["bids_dir"]
    if bids_dir is None:
        raise ValueError(f"Configure datasets.{dataset}.bids_dir before running this dataset.")
    config["bids_dir"] = bids_dir
    return config


def module_path(config: dict, module: str, kind: str) -> Path:
    """Keep products under their producing module, dataset and rest task."""
    roots = {
        "interim": "data/interim/neuroimaging",
        "processed": "data/processed/neuroimaging",
        "tables": "outputs/tables/neuroimaging",
        "logs": "outputs/logs/neuroimaging",
        "temp": "temp/neuroimaging",
    }
    return Path(config["project_root"]) / roots[kind] / module / config["dataset"] / "rest"


def shell_config(config: dict, stage: str, subject: str) -> None:
    """Export configured values and module paths; scientific command lines live in sbatch scripts."""
    tools = config["tools"]
    output = module_path(config, stage, "interim")
    values = dict(
        PROJECT_ROOT=Path(config["project_root"]).as_posix(), BIDS_DIR=Path(config["bids_dir"]).as_posix(),
        OUTPUT_DIR=output.as_posix(), WORK_DIR=(output.parent / "work" / subject).as_posix(),
        TEMP_DIR=(module_path(config, stage, "temp") / subject / os.environ.get("SLURM_JOB_ID", "manual")).as_posix(),
        LOG_DIR=module_path(config, stage, "logs").as_posix(),
        FMRIPREP_DIR=module_path(config, "fmriprep", "interim").as_posix(),
        FREESURFER_DIR=(Path(config["project_root"]) / "data/interim/neuroimaging/freesurfer" / config["dataset"]).as_posix(),
        IMAGE=tools[stage + "_image"], FS_LICENSE=tools["fs_license"],
        TEMPLATEFLOW=tools["templateflow"], SINGULARITY_MODULE=tools["singularity_module"],
        ATLAS_NAMES=list(config["atlases"]),
        ATLAS_BINDS=[f"{host}:/atlases/{name}:ro" for name, host in tools["atlas_datasets"].items()],
        ATLAS_DATASETS=[f"{name}=/atlases/{name}" for name in tools["atlas_datasets"]],
    )
    values.update({f"{stage}_{key}".upper(): value for key, value in config[stage].items()})
    for name, value in values.items():
        if isinstance(value, list):
            print(f"{name}=({' '.join(shlex.quote(str(item)) for item in value)})")
        else:
            print(f"{name}={shlex.quote(str(value))}")
