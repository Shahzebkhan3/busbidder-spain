# BusBidder Spain

BusBidder Spain compares and books simulated bus journeys from Madrid. It filters offers by traveller requirements and ranks the matches using configurable weights. ACIT4420 final project, OsloMet (2026).

## Start the desktop app

Use Python 3.10 or later with Tcl/Tk support. The project was tested on Python 3.14.3. From the repository root in PowerShell, set up the environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Run this command to open the **Tkinter GUI**, the main interface:

```powershell
python -m busbidder
```

Enter your trip requirements and scoring preferences, then select **Search offers**. Select a ranked offer to see its scores and fare terms. To try a booking with separate practice data, open the GUI with `python -m busbidder --bookings-file logs/gui-demo.sqlite3`.

## Data and dependencies

- `data/companies.csv`, `data/destinations.csv`, and `data/offers.csv` are the input files. Traveller presets are in `data/profiles.json`.
- The app uses the Python standard library, including Tkinter and SQLite. `requirements.txt` lists pytest for the tests.

## Run the tests and reproduce the results

From the repository root, run:

```powershell
python -m pytest tests -q
python scripts/generate_offers.py --check
python -m busbidder --compare
```

The second command checks that the committed offer dataset matches the generator. The last command recreates `results/profile_comparison.csv` and `results/ranking_sensitivity.csv` for the report.

For optional terminal commands, run `python -m busbidder --help`.
