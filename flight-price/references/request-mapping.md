# Request mapping

Map natural-language requests to the generic CLI before querying. Never hardcode a route.

## Required fields

| Field | Examples | CLI |
|---|---|---|
| Origin | 香港, 深圳, HKG, SZX | positional `origin` |
| Destination | 米兰, 东京, MXP, NRT | positional `dest` |
| Outbound date/range | 6 月, 10 月 3 日, next month | `--depart`, optional `--to` |
| Trip type | 单程, 往返, one-way, round trip | `--trip-type` |
| Duration | 玩 8 天, 住 8 晚 | `--days 8` or `--stay 8` |

## Chinese and English aliases

| Meaning | Accepted input |
|---|---|
| One-way | 单程, one-way, one way, OW |
| Round-trip | 往返, 来回, round-trip, round trip, RT |
| Stay 8 nights | 住 8 晚, 8 nights, stay 8 |
| Travel 8 days | 玩 8 天, 8 days, trip 8 days |
| Date range | 6 月, June, 10 月 3 日到 10 月 10 日 |

## Inference

1. `玩 N 天` means `--days N`, which becomes `N-1` nights.
2. `住 N 晚` means `--stay N`, unchanged.
3. Return date, stay nights, or total days imply round-trip.
4. No return information implies one-way.
5. A month-only request scans from the first to the last day of that month.
6. If the year is missing and the month is in the past, ask for the year.
7. If origin or destination is missing or ambiguous, ask one short question.

## Examples

### Round-trip by month and total days

Input:

```text
2027 年 6 月香港到米兰，玩 8 天，往返，生成 PDF
```

Mapping:

```text
origin=HKG dest=MXP
--trip-type roundtrip --days 8
--depart 2027-06-01 --to 2027-06-30
```

### Round-trip by nights

```text
深圳到东京，10 月出发，住 8 晚，找最便宜
```

```text
origin=SZX dest=TYO
--trip-type roundtrip --stay 8
--depart 2027-10-01 --to 2027-10-31
```

### One-way fixed date

```text
广州飞巴黎，单程，2027 年 4 月 3 日
```

```text
origin=CAN dest=PAR
--trip-type oneway
--depart 2027-04-03 --to 2027-04-03
```

If the city code is ambiguous, resolve it to the city code accepted by `flight-price` such as `PAR`, `TYO`, or `LON`.
