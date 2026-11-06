---
name: flight-price
description: Query and summarize bookable Trip.com flight prices for any origin and destination with the `flight-price` CLI. Use when the user provides an origin, destination, travel month/date range, trip days or nights, and one-way or round-trip intent, or asks to compare dates or airports, identify baggage-inclusive fares, list operating aircraft types when available, or export flight results to PDF, DOCX, or XLSX. Trigger phrases include 查机票, 比价, 单程机票, 往返机票, 往返 8 晚, 玩 8 天, 生成机票 PDF, 找便宜机票, 多日期机票, 含托运行李机票, 导出 Excel 机票, 输出 Word 机票.
---

# flight-price

A CLI tool that queries **Trip.com** for real, currently-bookable flight prices across a date range or a list of explicit (outbound, return) date pairs. Designed for AI agents. The default workflow is one atomic wrapper call that saves raw JSON locally, creates a PDF, and prints only a compact result summary.

## Trigger phrases

Invoke this skill for requests such as:

- `查机票`
- `比价`
- `单程机票`
- `往返机票`
- `往返 8 晚`
- `玩 8 天`
- `生成机票 PDF`
- `找便宜机票`
- `比较多日期机票`
- `含托运行李机票`
- `导出机票 Excel`

## Natural-language request mapping

Accept any origin and destination, not just HKG-MXP. Extract these fields before querying:

| User input | Query mapping |
|---|---|
| `香港到米兰` / `HKG to MXP` | `origin=HKG`, `dest=MXP` |
| `单程` / `one-way` | `--trip-type oneway` |
| `往返` / `round trip` | `--trip-type roundtrip` |
| `玩 8 天` | `--days 8` (inclusive days, becomes 7 nights) |
| `住 8 晚` / `8 nights` | `--stay 8` |
| `6 月` | scan 06-01 through 06-30 unless specific dates are given |
| `10 月 3 日出发` | fixed `--depart 10-03` and `--to` same date |

Inference rules:

- Mentions of return dates, stay nights, or trip days imply round-trip.
- A request with only an outbound date and no return information implies one-way.
- Convert `玩 N 天` to `N-1` nights; keep `N 晚` unchanged.
- If origin or destination is missing, ask one short clarification.
- If the month is ambiguous relative to today, ask for the year.
- State any inferred assumption in the final answer.

Detailed mapping examples are in [references/request-mapping.md](references/request-mapping.md).

## Query architecture

`flight-price` extracts Trip.com's `FlightListSearch` response data. Do not replace it with DOM text scraping for normal queries. Use [diagnose_trip.py](scripts/diagnose_trip.py) only to investigate page/API failures. The diagnostic helper degrades through CSS selectors, text selectors, and regex markers, while saving a screenshot instead of dumping HTML.

## Fast path: query and PDF in one command

Use `scripts/run_flight_query.py` for a complete flight request. It invokes `flight-price`, writes raw JSON to a temporary file, generates a PDF, and prints only the paths and cheapest itinerary.

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/flight-price"
python3 "$SKILL_DIR/scripts/run_flight_query.py" ORIGIN DEST \
  --trip-type roundtrip --days 8 \
  --depart 2027-06-01 --to 2027-06-30 \
  --formats pdf \
  --output "/path/to/ORIGIN-DEST-2027-06.pdf" \
  --top 10 \
  --title "机票汇总"
```

For one-way:

```bash
python3 "$SKILL_DIR/scripts/run_flight_query.py" SZX NRT \
  --trip-type oneway --depart 2027-04-03 --to 2027-04-03 \
  --formats pdf --output "/path/to/SZX-NRT-2027-04.pdf"
```

Add `--formats pdf,xlsx,docx` only when those formats are requested. Add `--cache` for a repeat scan; omit it for a final booking check. Pass `--keep-json` only when the user asks for the source data.

Use `flight_report.py` only when a JSON result already exists. Never print the JSON before calling either script.

The default PDF includes query time, currency, source URL, total-price basis, baggage, stops, refund/change status, ticketing provider, aircraft, and a direct-flight value hint. Fields without trustworthy data remain blank or say `见出票页`.

See [references/schema.md](references/schema.md) for normalized report fields and source limitations. A sanitized example is available in [assets/sample-report.pdf](assets/sample-report.pdf).

## Mandatory low-token protocol

Apply these rules to every invocation:

1. **Never echo raw data.** Save JSON to a temporary file or cache file. Do not print full JSON, HTML, all `flights[]`, or all `results[].options[]` to the terminal or conversation.
2. **Pre-truncate all visible output.** Keep every tool result under 500 characters unless the user explicitly requests a larger format. Print only paths, counts, key fields, and the best few itineraries.
3. **Use one atomic batch pass.** Scan all requested dates and airports in one scripted run. Do not self-loop, repeatedly rescan, or retry successful queries. Retry a specific query once only when its status is `timeout`.
4. **Generate files, not console dumps.** Write raw JSON to disk, then let `scripts/run_flight_query.py` or `scripts/flight_report.py` produce PDF, DOCX, or XLSX. Read only its compact summary.
5. **Never invent missing fields.** The CLI output does not reliably include baggage allowance or aircraft type. Leave those fields blank unless they were extracted from a trustworthy source.

## When to invoke this skill

Use this skill whenever the user's request involves any of:
- Finding the cheapest flight on a specific date or across a date range
- Comparing prices for different stay-length / departure-date combinations (typical "should I travel Friday or Saturday?" style)
- Holiday-planning queries that require enumerating leave-day combinations ("端午 + 请1天假怎么去 X 最划算？")
- Filtering flights by airline, max stops, depart-time window
- Producing a JSON-structured list of candidate itineraries for downstream decision-making

Don't use this for: hotel pricing, ground transportation, visa info, airline schedules without prices.

## Installation check + self-diagnostic

Before invoking the CLI, verify it's installed:

```bash
which flight-price && flight-price --version
```

If missing, the user must install it. Point them at: https://github.com/daghlny/flight-price-skill (one-line installer in the README).

**If a query fails with timeout / unexpected error**, run the built-in self-check:

```bash
flight-price doctor --json
```

It checks (in order): python version, package install, playwright import, Chromium binary, DNS/HTTPS to tw.trip.com, and a live BJS-SHA query. Each failed check returns a `hint` field with the fix. Tell the user to follow the hint of the first failed check — fixing earlier ones often clears later ones automatically.

## Recommended invocation pattern for agents

**Always pass `--json` and redirect it to a file.** The default human-table output is harder to parse; JSON is structured and stable, but the raw JSON must not be printed.

**Inspect `flights[]` programmatically** (the top-level flat array) and write only selected fields to a file or report. Do not dump the array into chat.

**Check `results[i].status` programmatically.** Distinguish `"ok"`, `"no_results"`, and `"timeout"`. Retry only a specific `"timeout"` once.

**Enable `--cache` when iterating.** Set `--cache` on the first multi-date call. Subsequent refinements using the same dates can reuse the cached raw response. Do not turn cache on for final booking checks.

**Do NOT use `--cache` when** the user is about to book (they need THE current price), or when running a periodic monitor (every run should be fresh).

### Retry and diagnostics

`run_flight_query.py` retries a failed query once by default. It does not retry `no_results`.

On a final failure, it writes short diagnostics without printing raw data:

- `<diagnostics>/stderr.txt`
- `<diagnostics>/doctor.json`
- `<diagnostics>/diagnose-trip.json`
- `<diagnostics>/trip-page-*.png`

Pass `--diagnostics-dir` (or use the default `./flight-diagnostics`) and inspect only the short JSON summary. The diagnostic page uses headless Chromium, `viewport=1440x900`, `locale=en-US`, and `timezone=Asia/Hong_Kong`.

### Report formats

`run_flight_query.py` defaults to PDF only. Use `--formats pdf,xlsx,docx` to create additional files. The PDF is designed for the final answer; XLSX is for full candidate rows and manual sorting; DOCX is for editable narrative summaries.

Use the Python runtime that has `reportlab`, `python-docx`, and `openpyxl`. In Codex desktop, load workspace dependencies and use the bundled Python executable. Do not install new packages just for a report.

### Single-date or contiguous-range scan

```bash
flight-price BJS SHA --from 2026-06-01 --to 2026-06-07 --json > /tmp/flight-price.json
flight-price BJS TYO --rt --stay 2 --from 2026-06-19 --to 2026-06-19 --json > /tmp/flight-price.json
flight-price BJS NRT --rt --return-date 2026-06-15 --from 2026-06-10 --to 2026-06-14 --json > /tmp/flight-price.json
```

### Multi-combination scan (the agent-native form)

When the user's question implies several itinerary variants — typical of holiday planning, leave-day optimization, or "compare these specific date pairs" — compute the date pairs yourself and pass them in one call:

```bash
flight-price BJS HGH --pairs \
  2026-06-18:2026-06-20,2026-06-18:2026-06-21,\
  2026-06-19:2026-06-21,2026-06-19:2026-06-22,\
  2026-06-20:2026-06-22 \
  --json --max-stops 0 > /tmp/flight-price.json
```

Each pair is `OUT[:RET]` (omit `:RET` for one-way). Mutually exclusive with `--from/--to/--rt/--stay/--return-date`.

## CLI surface (cheat sheet)

```
flight-price ORIGIN DEST [date selection] [filters] [ranking] [output]
```

| Group | Flag | Notes |
|---|---|---|
| Date range | `--from YYYY-MM-DD` / `--to YYYY-MM-DD` | default: today / from + 7 |
| Round-trip | `--rt --stay N` or `--rt --return-date YYYY-MM-DD` | RT mode |
| Explicit pairs | `--pairs OUT[:RET][,OUT[:RET]...]` | mutually exclusive with above |
| Trip composition | `--cabin {economy,premium,business,first}`, `--adults N`, `--currency CODE` | default: economy / 1 / CNY |
| Filters | `--direct`, `--max-stops N`, `--airline CA,MU`, `--exclude-airline IJ`, `--depart-after HH:MM`, `--depart-before HH:MM` | apply to OUTBOUND leg |
| Ranking | `--sort {price,duration,depart}`, `--limit N\|all` | default sort=price, limit=1 (table) / 5 (--json) |
| Cache | `--cache`, `--cache-ttl SECONDS` | opt-in; enable for agent loops, leave off for booking |
| Perf | `--concurrency N` | default 3, raise to 5-8 for big scans |
| Output | `--json` | structured, agent-friendly |
| Auxiliary | `flight-price doctor \| help \| man \| --version` | docs + self-check |

ORIGIN / DEST accept either 3-letter IATA city codes (BJS = any Beijing airport, SHA = any Shanghai, TYO = any Tokyo) or specific airport codes (PEK, PVG, NRT, HND).

## JSON output schema

Top-level:

```jsonc
{
  "origin": "BJS",
  "dest": "HGH",
  "mode": "OW" | "RT" | "PAIRS",
  "date_from": "2026-06-18",
  "date_to": "2026-06-22",
  "filters": { "direct": false, "max_stops": null, "airline": null, ... },
  "sort": "price",
  "limit": 5,
  "results": [ /* per-query, see below */ ],
  "flights": [ /* FLAT array, ranked across all queries — READ THIS FIRST */ ]
}
```

Each `results[i]`:

```jsonc
{
  "date": "2026-06-19",
  "return_date": "2026-06-22",
  "stay_nights": 3,          // null for one-way
  "status": "ok" | "no_results" | "timeout",
  "n_options_total": 39,     // before filter+limit
  "n_options_returned": 5,
  "options": [ /* FlightOption list */ ]
}
```

Each `flights[i]` (and `options[j]`) is a `FlightOption`:

```jsonc
{
  "price": 1460.0,
  "currency": "CNY",
  "direct": true,                // outbound is non-stop
  "airline": "CA",                // outbound first-segment carrier
  "flight_nos": ["CA1732"],       // outbound flight numbers
  "segments": [ /* full outbound detail: airport, terminal, time, duration */ ],
  "layovers": [ /* outbound layovers if any */ ],
  "return_flights": [             // RT only; empty array for OW
    {"flight_no": "CA8367", "airline": "CA", "depart_time": "2026-06-22 07:55:00"}
  ],
  "return_stops": 0,
  "return_direct": true,
  "depart_time": "2026-06-19 21:35:00",
  "total_duration_min": 155,
  // flights[] entries also carry date / return_date / stay_nights for context
  "date": "2026-06-19",
  "return_date": "2026-06-22",
  "stay_nights": 3
}
```

## Status field semantics — important for retry decisions

| status | meaning | agent action |
|---|---|---|
| `ok` | Trip.com returned ≥1 itinerary | use the data |
| `no_results` | Trip.com responded but had no matching flights | do NOT retry — accept "no flights" as the answer |
| `timeout` | The query hit the 30s timeout before Trip.com responded | retry that specific query (just rerun with same args, or use a more targeted scan) |

## Known limitations the agent should be aware of

- **Return-leg detail is partial**: for RT, only return flight numbers + depart times are surfaced. Transit airport, arrive time, and durations of the return leg are NOT in the response (they live behind a separate API call the CLI doesn't make).
- **Per-query cost is ~10 seconds** (one Chromium navigation each). A 30-date scan takes ~100s with default concurrency 3. With `--cache`, subsequent same-key calls are ~50ms.
- **Children/infant passengers not parameterized** — only `--adults N`. For family pricing the actual booking will differ.
- **Cache is OFF by default** — opt in via `--cache` for agent iteration loops.

## Common patterns

**Cheapest weekend across a month:**
```bash
flight-price BJS HGH --rt --stay 2 --from 2026-07-04 --to 2026-07-25 --direct --json
```

**Direct flights only, after-work departures:**
```bash
flight-price BJS SHA --depart-after 18:00 --max-stops 0 --json
```

**Holiday-shifted RT combinations** (agent computes the pairs from the holiday calendar in its head):
```bash
flight-price BJS HGH --pairs 2026-06-19:2026-06-21,2026-06-19:2026-06-22,2026-06-20:2026-06-22 --json
```

**One specific itinerary "is this in inventory and what's the price":**
```bash
flight-price BJS NRT --rt --return-date 2026-06-15 --from 2026-06-10 --to 2026-06-10 --direct --json
```

## Don't

- Don't try to combine `--pairs` with `--from/--to/--rt/--stay/--return-date` — the CLI will exit 2 with an error.
- Don't drop `--json` when relaying results back to a calling system; the human table is not stable for parsing.
- Don't use `cat`, `head`, `jq .`, or similar commands to print the saved JSON. Parse it with the report script or a small field extractor.
- Don't print more than 10 rows. Prefer 3-5 rows plus the report file.
- Don't retry on `"no_results"` — the answer is genuine.
- Don't assume `return_flights` has `arrive_time` or `airport` — those fields don't exist on the return leg.
- Don't query date ranges in the past — Trip.com returns empty.

## Reference

- Source / issues: https://github.com/daghlny/flight-price-skill
- Full CLI manual: `flight-price man`
