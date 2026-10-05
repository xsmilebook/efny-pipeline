"""Resolve the shared neuroimaging configuration and module-owned paths."""

import json
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
