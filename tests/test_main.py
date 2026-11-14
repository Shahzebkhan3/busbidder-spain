"""Check the package command and actual file logging from a clean project copy."""

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


PROJECT_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def app_dir(tmp_path):
    project = tmp_path / "project"
    shutil.copytree(PROJECT_DIR / "busbidder", project / "busbidder")
    shutil.copytree(PROJECT_DIR / "data", project / "data")
    return project


def run_app(app_dir, *args):
    env = dict(os.environ, PYTHONPATH="", PYTHONIOENCODING="utf-8")
    return subprocess.run(
        [sys.executable, "-B", "-m", "busbidder", *args],
        cwd=app_dir, env=env, capture_output=True, text=True, encoding="utf-8",
        timeout=20,
    )


def test_command_loads_sample_and_writes_log(app_dir):
    result = run_app(app_dir)
    assert result.returncode == 0, result.stderr
    assert "Loaded 6 valid offers." in result.stdout
    assert "O5 | NocheVia" in result.stdout
    assert "2027-07-14 07:30" in result.stdout
    assert "Loaded 5 companies, 15 destinations and 6 offers" in (
        app_dir / "logs" / "busbidder.log"
    ).read_text(encoding="utf-8")


def test_command_reports_missing_data_without_traceback(app_dir):
    result = run_app(app_dir, "--data-dir", str(app_dir / "missing"))
    assert result.returncode == 1
    assert "Unable to load marketplace data" in result.stderr
    assert "companies.csv" in result.stderr
    assert "Traceback" not in result.stderr
    assert "Marketplace load failed" in (
        app_dir / "logs" / "busbidder.log"
    ).read_text(encoding="utf-8")


def test_command_can_read_a_selected_data_directory(app_dir):
    selected = app_dir / "alternative"
    shutil.copytree(app_dir / "data", selected)
    (selected / "offers.csv").write_text(
        (selected / "offers.csv").read_text(encoding="utf-8").splitlines()[0] + "\n",
        encoding="utf-8",
    )
    result = run_app(app_dir, "--data-dir", str(selected))
    assert result.returncode == 0, result.stderr
    assert "Loaded 0 valid offers." in result.stdout
