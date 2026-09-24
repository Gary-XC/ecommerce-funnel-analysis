"""
Central configuration for paths and project constants
- Avoids the hard-coded relative paths scattered across notebooks and scripts
- Makes the project runnable from different working directories
- Provides a single place to update data locations later
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
SAMPLE_DATA_DIR = DATA_DIR / "sample"

NOTEBOOKS_DIR = PROJECT_ROOT / "notebooks"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
DOCS_DIR = PROJECT_ROOT / "docs"
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"

FUNNEL_EVENT_TYPES = [
    "view",
    "cart",
    "remove_from_cart",
    "purchase",
]

PRIMARY_FUNNEL_STAGES = [
    "view",
    "cart",
    "purchase",
]


def ensure_data_dirs() -> None:
    """
    Create expected data directories if they do not exist.

    This is useful for collaborators cloning the repo.
    It does not download data; it only prepares the folder structure.
    """
    for directory in [RAW_DATA_DIR, PROCESSED_DATA_DIR, SAMPLE_DATA_DIR]:
        directory.mkdir(parents=True, exist_ok=True)
