# flight-price-pdf-skill

[中文](README.md) | [English](README.en.md)

A local Codex skill for querying live Trip.com flight prices for any origin and destination, then generating a PDF automatically. The core design is **"auto-end, script runs"**: the agent launches `run_flight_pdf.py` with one command and immediately ends its turn; the script finishes everything on its own — full-window scan → one automatic timeout retry → auto-started summary (dedupe, compare, Chinese report) → PDF rendered by Playwright. Raw JSON only lives in a temp dir and is discarded; the conversation never sees more than 3 summary lines, minimizing token usage. Supports one-way/round-trip, "N days" or "N nights".

## Features

- Uses the `flight-price` CLI with headless Chromium through Playwright
- **v0.4: new `run_flight_pdf.py` end-to-end script** — multi-origin × date-window in one command (scan → one automatic timeout retry → summary → Chinese HTML → PDF via Playwright, **no reportlab needed**, runs on Python 3.9+); prints ≤3 summary lines
- Agent protocol: launch long scans as a background job and end the turn; the script finishes the PDF on its own with zero raw-JSON round-trips
- The CLI and the rendering interpreter are auto-resolved via `PATH`, `~/.local/bin`, and `~/.flight-price-skill/.venv`
- Generates PDF by default; XLSX and DOCX stay optional through `flight_report.py`
- Keeps raw JSON on disk and prints only a compact summary
- Accepts any origin/destination, one-way/round-trip, date range, airline, and stop filters
- Maps "8 days" to 7 nights and keeps "8 nights" as 8 nights
- Never guesses baggage, aircraft, refund, or ticketing fields
- Adds comparison columns for price basis, baggage, stops, refund/change, ticketing provider, and aircraft
- Highlights a direct-flight alternative when the cheapest itinerary is not direct
- Retries a failed query once and writes short diagnostics with screenshots

## Structure

```text
flight-price/
├── SKILL.md
├── agents/openai.yaml
├── references/
│   ├── schema.md
│   └── request-mapping.md
├── assets/sample-report.pdf
└── scripts/
    ├── run_flight_pdf.py     # v0.4 end-to-end: scan + retry + summary + PDF
    ├── run_flight_query.py
    ├── flight_report.py
    └── diagnose_trip.py
examples/
├── 大湾区-羽田-往返机票-2027年6-7月.json  # live merged data (rows carry `origin`)
├── 大湾区-羽田-往返机票-2027年6-7月.pdf   # live comparison report
├── HKG-MXP-sample.json
├── flat-scan-sample.json
└── HKG-MXP-sample.pdf
tests/
├── test_run_flight_pdf.py
└── test_report.py
```

## Install

Download the ZIP from a Release, then extract it into the Codex skills directory:

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
unzip flight-price-pdf-skill.zip -d "${CODEX_HOME:-$HOME/.codex}/skills"
```

Or clone the repository and run:

```bash
./install.sh
```

## Usage

### v0.4 end-to-end one-liner (multi-airport / date-window comparison, recommended)

```bash
python3 "$HOME/.codex/skills/flight-price/scripts/run_flight_pdf.py" HKG,SZX,CAN,MFM HND \
  --days 7 --depart 2027-06-20 --to 2027-07-25 \
  --clamp-return 2027-07-31 --airline UO,NH,CX \
  --title "GBA to Haneda summer 2027" --output out.pdf
```

The script scans the whole window, retries timed-out pairs once, dedupes rows, writes a Chinese HTML report, renders the PDF with Playwright, and prints ≤3 summary lines. Intermediate JSON lives in a temp dir and is discarded (use `--keep-json` to keep a merged raw file). One-way: `--trip-type oneway`; summary without PDF: `--no-pdf`.

Start a new Codex conversation and say:

```text
Use $flight-price to search HKG to MXP in June 2027, 8 days, round trip, and generate a PDF.
Use $flight-price to search SZX to NRT on 2027-04-03, one way, and generate a PDF.
```

Run the entry point directly:

```bash
python3 "$HOME/.codex/skills/flight-price/scripts/run_flight_query.py" HKG MXP \
  --trip-type roundtrip --days 8 \
  --depart 2027-06-01 --to 2027-06-30 \
  --formats pdf \
  --output "./ORIGIN-DEST-2027-06.pdf" \
  --title "Flight summary"
```

One-way example:

```bash
python3 "$HOME/.codex/skills/flight-price/scripts/run_flight_query.py" SZX NRT \
  --trip-type oneway \
  --depart 2027-04-03 --to 2027-04-03 \
  --output "./SZX-NRT-2027-04.pdf"
```

Request Word or Excel with:

```bash
--formats pdf,xlsx,docx
```

Diagnostics are written to `./flight-diagnostics` on a final failure:

```bash
python3 "$HOME/.codex/skills/flight-price/scripts/run_flight_query.py" HKG MXP \
  --trip-type roundtrip --stay 8 \
  --depart 2027-06-10 --to 2027-07-01 \
  --diagnostics-dir "./flight-diagnostics"
```

Examples:

- Live artifacts (real run: HKG/SZX/CAN/MFM → Haneda, June–July 2027 window, 7-day trips, UO/NH/CX, 720 deduped quotes)
  - [Merged JSON](examples/大湾区-羽田-往返机票-2027年6-7月.json) (each row carries `origin`; timeout retries folded in)
  - [Comparison PDF](examples/大湾区-羽田-往返机票-2027年6-7月.pdf)
  - Prices/availability are a snapshot at query time, not current offers.
- Legacy sanitized fixtures (tests for `flight_report.py`)
  - [Sample JSON](examples/HKG-MXP-sample.json)
  - [Sample PDF](examples/HKG-MXP-sample.pdf)

## Dependencies

- `flight-price` CLI (installed to `~/.local/bin` by default; the scripts resolve it automatically)
- `run_flight_pdf.py` (v0.4 end-to-end path): Python 3.9+ only; the PDF is rendered by the Playwright runtime bundled with `flight-price`, **no reportlab / python-docx / openpyxl required**
- `run_flight_query.py` + `flight_report.py` (legacy path, DOCX/XLSX): Python 3.11+, `reportlab`, `python-docx`, `openpyxl`
- `pypdf` (full test suite only; affected tests auto-skip when missing)

In Codex desktop, use the Python executable from the workspace dependencies.

## Test

```bash
python3 -m unittest discover -s tests -v   # all offline, no network needed
```
