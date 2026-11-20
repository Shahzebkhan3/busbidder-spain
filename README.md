# BusBidder Spain

BusBidder Spain compares and books simulated bus journeys from Madrid. It filters offers by traveller requirements and ranks the matches using configurable weights. ACIT4420 final project, OsloMet (2026).

## Start the desktop app

Use Python 3.10 or later with Tcl/Tk support. The project was tested on Python 3.14.3. From the repository root in PowerShell, set up the environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Run this command to open the **Tkinter GUI**, the recommended way to use BusBidder:

```powershell
python -m busbidder
```

Enter your trip requirements and scoring preferences, then select **Search offers**. Select a ranked offer to see its scores and fare terms. To try a booking with separate practice data, open the GUI with `python -m busbidder --bookings-file logs/gui-demo.sqlite3`.

### Try the report example in the GUI

1. Choose **Malaga** and set **Earliest departure** to **2027-07-12** and **Latest departure** to **2027-07-14**.
2. Enter **50** for **Max. price (€)** and **1** for **Max. transfers**. Tick **Require a changeable ticket**.
3. Choose **Morning** for **Preferred departure**. Use **40**, **25**, **15**, and **20** for price, duration, departure, and flexibility, then select **Search offers**.

With an empty booking history, you should see four matches, with **Camino Express** first at **60.0**. Open **Rejected** to see why offers O1 and O6 were excluded.

## Project structure

```text
busbidder-spain/
├── busbidder/         Tkinter interface, terminal commands, and booking logic
├── data/              Input CSV files and traveller profiles
├── results/           Saved comparison CSVs used in the report
├── scripts/           Offer dataset generator
├── tests/             Automated tests
├── README.md          Setup and usage instructions
└── requirements.txt  Test dependency
```

## Data and dependencies

- `data/companies.csv`, `data/destinations.csv`, and `data/offers.csv` are the input files. Traveller presets are in `data/profiles.json`.
- The app uses the Python standard library. Tkinter comes with Python installations that include Tcl/Tk support. Run `python -m tkinter` to check that a small demo window opens.

## Run the tests and reproduce the results

From the repository root with the virtual environment active, install pytest, the dependency listed in `requirements.txt`.

```powershell
python -m pip install -r requirements.txt
```

Run the automated tests in `tests/`. The `-q` flag keeps the output brief.

```powershell
python -m pytest tests -q
```

Check that the offer generator reproduces the submitted dataset in `data/offers.csv`.

```powershell
python scripts/generate_offers.py --check
```

Rank the same Malaga offers for three traveller profiles and compare both price-scoring methods with and without offer O5. Each run starts from the seat counts in `data/offers.csv`. The command writes `results/profile_comparison.csv` and `results/ranking_sensitivity.csv`, which provide the data for Tables 2 and 3 in the report.

```powershell
python -m busbidder --compare
```

## Optional terminal search

Use the Tkinter GUI for the normal search and booking workflow. For a quick terminal check, this command searches for changeable tickets to Malaga from 12 to 14 July 2027, with a €50 budget, up to one transfer, and a preference for morning departures.

```powershell
python -m busbidder --destination Malaga --from-date 2027-07-12 --to-date 2027-07-14 --max-price 50 --max-transfers 1 --require-changeable --departure morning
```

The terminal prints the ranked matches and why offers were rejected. Run `python -m busbidder --help` to see all terminal options.
