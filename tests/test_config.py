from ecommerce_funnel.config import (
    DATA_DIR,
    PROJECT_ROOT,
    RAW_DATA_DIR,
    PROCESSED_DATA_DIR,
    SAMPLE_DATA_DIR,
)


def test_project_root_exists() -> None:
    assert PROJECT_ROOT.exists()


def test_data_paths_are_under_data_directory() -> None:
    assert RAW_DATA_DIR.parent == DATA_DIR
    assert PROCESSED_DATA_DIR.parent == DATA_DIR
    assert SAMPLE_DATA_DIR.parent == DATA_DIR
