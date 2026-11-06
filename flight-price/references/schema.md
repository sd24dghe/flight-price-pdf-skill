# Flight report schema

The report normalizes `flight-price` JSON into one row per priced itinerary leg pair.

## Core fields

| Field | Meaning |
|---|---|
| `origin`, `dest` | Search route |
| `date`, `return_date`, `stay_nights` | Travel dates |
| `price`, `currency` | Query-time total price |
| `price_basis` | Defaults to `含税总价`; override only with source evidence |
| `airline` | First operating airline |
| `outbound_flights` | Outbound flight numbers |
| `outbound_route` | Outbound airport sequence |
| `depart_time` | First outbound departure |
| `outbound_duration` | First-to-last outbound segment duration |
| `stops` | Outbound transfer count |
| `return_flights` | Return flight numbers when supplied |
| `aircraft` | Aircraft only when supplied by a trustworthy source |
| `baggage` | Baggage allowance only when supplied |
| `refund_change` | Refund/change rule; defaults to `见出票页` |
| `provider` | Ticketing provider; defaults to `Trip.com（出票方见详情）` |
| `notes` | Direct/transfer summary |

## Source limitations

- `flight-price` returns bookable prices, not final booking guarantees.
- Prices can change between query and checkout.
- Return-leg airport, arrival time, and duration may be missing.
- Baggage, refund/change rules, ticketing provider, and aircraft may not be present in normal CLI JSON.
- Never infer a missing field. Leave it blank or mark `见出票页`.

## Aircraft and baggage extraction

When the user explicitly requests these fields, keep raw Trip.com payloads on disk and extract only:

- `journeyList[0].transSectionList[*].flightInfo.craftInfo`
- fare-policy `tagList` entries such as `FREE_CHECKED_BAGGAGE`

Do not print raw payloads. Merge only normalized values into the report input.

## Failure diagnostics

The wrapper retries a failed query once and writes:

- `stderr.txt`
- `doctor.json`
- `diagnose-trip.json`
- `trip-page-*.png`

Inspect the compact JSON summary and screenshot. Do not dump HTML.
