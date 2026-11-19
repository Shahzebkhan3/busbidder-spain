"""Keep tests that use the worked example separate from the full dataset."""

from pathlib import Path
import shutil

import pytest


@pytest.fixture
def sample_data(tmp_path: Path) -> Path:
    data = Path(__file__).resolve().parents[1] / "data"
    sample = tmp_path / "sample"
    sample.mkdir()
    for filename in ("companies.csv", "destinations.csv", "profiles.json"):
        shutil.copy2(data / filename, sample / filename)
    shutil.copy2(data / "malaga_sample.csv", sample / "offers.csv")
    return sample
