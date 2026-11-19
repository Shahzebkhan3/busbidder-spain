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


SEARCH_ARGS = ["--destination", "Malaga", "--from-date", "2027-07-12", "--to-date", "2027-07-14"]


def test_search_command_prints_matching_offers_and_reasons(app_dir):
    result = run_app(app_dir, *SEARCH_ARGS, "--max-price", "50", "--max-transfers", "1", "--require-changeable")
    assert result.returncode == 0, result.stderr
    assert "4 offers match your requirements." in result.stdout
    accepted, rejected = result.stdout.split("Rejected offers:")
    assert "O1 | SolRuta" not in accepted
    assert "O6 | Camino Express" not in accepted
    for offer_id in ("O2", "O3", "O4", "O5"):
        assert f"{offer_id} |" in accepted
    assert "O1 | Ticket must be changeable." in rejected
    assert "O6 | Price EUR 54.00 exceeds budget EUR 50.00." in rejected
    assert "Filtered 6 offers: 4 accepted, 2 rejected" in (
        app_dir / "logs" / "busbidder.log"
    ).read_text(encoding="utf-8")


def test_search_without_optional_limits_accepts_all_sample_offers(app_dir):
    result = run_app(app_dir, *SEARCH_ARGS)
    assert result.returncode == 0, result.stderr
    assert "6 offers match your requirements." in result.stdout
    assert "Rejected offers:" not in result.stdout


def test_search_with_no_matches_explains_rejections(app_dir):
    result = run_app(app_dir, *SEARCH_ARGS, "--max-price", "0")
    assert result.returncode == 0, result.stderr
    assert "No offers matched." in result.stdout
    assert result.stdout.count("exceeds budget EUR 0.00.") == 6


@pytest.mark.parametrize(
    "arguments,expected",
    [
        (["--max-price", "50"], "A search needs"),
        (["--require-changeable"], "A search needs"),
        ([*SEARCH_ARGS, "--max-price", "abc"], "--max-price must be a number"),
        ([*SEARCH_ARGS, "--max-price", "NaN"], "budget must be a finite number"),
        ([*SEARCH_ARGS, "--max-price", "-1"], "budget must be a finite number"),
        ([*SEARCH_ARGS, "--max-transfers", "-1"], "transfer limit"),
        ([*SEARCH_ARGS, "--max-transfers", "1.5"], "invalid int value"),
        ([*SEARCH_ARGS, "--to-date", "2027-07-11"], "last departure date"),
        ([*SEARCH_ARGS, "--from-date", "2027-02-30"], "--from-date"),
        ([*SEARCH_ARGS, "--destination", " "], "Enter a destination"),
    ],
)
def test_invalid_search_arguments_produce_helpful_errors(app_dir, arguments, expected):
    result = run_app(app_dir, *arguments)
    assert result.returncode == 2
    assert expected in result.stderr
    assert "Traceback" not in result.stderr
