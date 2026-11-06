#!/usr/bin/env python3
"""Run one flight-price query and emit only a compact PDF summary."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from flight_report import (
    collect_candidates,
    compact_summary,
    load_input,
    write_docx,
    write_pdf,
    write_xlsx,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origin")
    parser.add_argument("dest")
    parser.add_argument("--from", dest="date_from", help="outbound start date YYYY-MM-DD")
    parser.add_argument("--to", dest="date_to", help="outbound end date YYYY-MM-DD")
    parser.add_argument("--pairs", help="explicit OUT[:RET] pairs")
    parser.add_argument("--rt", action="store_true", help="round-trip mode")
    parser.add_argument("--stay", type=int, help="round-trip stay nights")
    parser.add_argument("--return-date", help="fixed return date YYYY-MM-DD")
    parser.add_argument("--direct", action="store_true")
    parser.add_argument("--max-stops", type=int)
    parser.add_argument("--airline")
    parser.add_argument("--exclude-airline")
    parser.add_argument("--depart-after")
    parser.add_argument("--depart-before")
    parser.add_argument("--limit", type=int, default=20, help="itineraries per date")
    parser.add_argument("--sort", choices=("price", "duration", "depart"), default="price")
    parser.add_argument("--cabin", choices=("economy", "premium", "business", "first"), default="economy")
    parser.add_argument("--adults", type=int, default=1)
    parser.add_argument("--currency", default="CNY")
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--cache", action="store_true")
    parser.add_argument("--output", help="PDF path or output stem")
    parser.add_argument("--formats", default="pdf", help="comma-separated: pdf,xlsx,docx")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--title")
    parser.add_argument("--source", default="Trip.com / flight-price")
    parser.add_argument("--keep-json", help="optional path for the raw query JSON")
    return parser.parse_args()


def build_command(args: argparse.Namespace, executable: str) -> list[str]:
    if args.pairs and (args.date_from or args.date_to or args.rt or args.stay or args.return_date):
        raise ValueError("--pairs cannot be combined with --from/--to/--rt/--stay/--return-date")
    if args.pairs and (not args.date_from and not args.date_to):
        pass
    elif not args.date_from:
        raise ValueError("--from is required unless --pairs is used")

    command = [executable, args.origin.upper(), args.dest.upper()]
    if args.pairs:
        command += ["--pairs", args.pairs]
    else:
        command += ["--from", args.date_from]
        if args.date_to:
            command += ["--to", args.date_to]
        if args.stay is not None or args.return_date:
            command += ["--rt"]
        if args.stay is not None:
            command += ["--stay", str(args.stay)]
        if args.return_date:
            command += ["--return-date", args.return_date]

    if args.direct:
        command.append("--direct")
    elif args.max_stops is not None:
        command += ["--max-stops", str(args.max_stops)]
    if args.airline:
        command += ["--airline", args.airline]
    if args.exclude_airline:
        command += ["--exclude-airline", args.exclude_airline]
    if args.depart_after:
        command += ["--depart-after", args.depart_after]
    if args.depart_before:
        command += ["--depart-before", args.depart_before]

    command += [
        "--limit",
        str(args.limit),
        "--sort",
        args.sort,
        "--cabin",
        args.cabin,
        "--adults",
        str(args.adults),
        "--currency",
        args.currency,
        "--concurrency",
        str(args.concurrency),
        "--json",
    ]
    if args.cache:
        command.append("--cache")
    return command


def parse_formats(value: str) -> set[str]:
    formats = {part.strip().lower() for part in value.split(",") if part.strip()}
    unsupported = formats - {"pdf", "xlsx", "docx"}
    if unsupported:
        raise ValueError(f"unsupported format(s): {', '.join(sorted(unsupported))}")
    if not formats:
        raise ValueError("--formats cannot be empty")
    return formats


def resolve_paths(args: argparse.Namespace, formats: set[str]) -> tuple[Path | None, Path | None, Path | None]:
    if args.output:
        requested = Path(args.output).expanduser().resolve()
        stem = requested.with_suffix("") if requested.suffix.lower() in {".pdf", ".xlsx", ".docx"} else requested
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M")
        stem = Path.cwd() / f"flight_{args.origin.upper()}_{args.dest.upper()}_{stamp}"

    pdf = stem.with_suffix(".pdf") if "pdf" in formats else None
    xlsx = stem.with_suffix(".xlsx") if "xlsx" in formats else None
    docx = stem.with_suffix(".docx") if "docx" in formats else None
    return pdf, xlsx, docx


def short_error(text: str, limit: int = 450) -> str:
    clean = " ".join(text.split())
    return clean[:limit]


def main() -> None:
    args = parse_args()
    if args.top < 1:
        raise ValueError("--top must be at least 1")
    formats = parse_formats(args.formats)

    executable = shutil.which("flight-price")
    if not executable:
        raise ValueError(
            "flight-price is not installed; see https://github.com/daghlny/flight-price-skill"
        )

    command = build_command(args, executable)
    pdf, xlsx, docx = resolve_paths(args, formats)

    with tempfile.TemporaryDirectory(prefix="flight-price-") as temp_dir:
        json_path = Path(temp_dir) / "result.json"
        with json_path.open("w", encoding="utf-8") as output:
            completed = subprocess.run(
                command,
                stdout=output,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
        if completed.returncode != 0:
            message = short_error(completed.stderr or "flight-price failed")
            raise ValueError(message)

        data = load_input(json_path)
        rows = collect_candidates(data)
        if not rows:
            raise ValueError("no priced itineraries found")

        if args.keep_json:
            keep_path = Path(args.keep_json).expanduser().resolve()
            keep_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(json_path, keep_path)

    title = args.title or f"{args.origin.upper()}-{args.dest.upper()} 机票汇总"
    if pdf:
        write_pdf(pdf, rows, data, args.top, title, args.source)
    if xlsx:
        write_xlsx(xlsx, rows, data, args.top, title, args.source)
    if docx:
        write_docx(docx, rows, data, args.top, title, args.source)

    print(compact_summary(rows, pdf, xlsx, docx))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {short_error(str(exc))}")
        raise SystemExit(1)
