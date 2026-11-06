#!/usr/bin/env python3
"""Capture a short Trip.com page diagnostic without dumping HTML."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from playwright.async_api import async_playwright


FLS_PATH = "/restapi/soa2/27015/FlightListSearch"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origin")
    parser.add_argument("dest")
    parser.add_argument("--date", required=True)
    parser.add_argument("--return-date")
    parser.add_argument("--outdir", default="./flight-diagnostics")
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--currency", default="CNY")
    return parser.parse_args()


def build_url(args: argparse.Namespace) -> str:
    origin = args.origin.upper()
    dest = args.dest.upper()
    params = {
        "dcity": origin.lower(),
        "acity": dest.lower(),
        "ddate": args.date,
        "dairport": origin.lower(),
        "aairport": dest.lower(),
        "triptype": "rt" if args.return_date else "ow",
        "class": "y",
        "lowpricesource": "searchform",
        "quantity": 1,
        "searchboxarg": "t",
        "nonstoponly": "off",
        "locale": "en-US",
        "curr": args.currency.upper(),
    }
    if args.return_date:
        params["rdate"] = args.return_date
    return "https://tw.trip.com/chinaflights/showfarefirst?" + urlencode(params)


async def inspect_page(args: argparse.Namespace) -> dict:
    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    screenshot_path: Path | None = outdir / f"trip-page-{stamp}.png"
    url = build_url(args)
    captured: dict[str, object] = {}
    done = asyncio.Event()

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="en-US",
            timezone_id="Asia/Hong_Kong",
            user_agent=UA,
            viewport={"width": 1440, "height": 900},
        )
        page = await context.new_page()

        async def capture_response(response) -> None:
            if FLS_PATH not in response.url:
                return
            try:
                body = await response.text()
            except Exception:
                body = ""
            captured["response_status"] = response.status
            captured["body_length"] = len(body)
            captured["has_itinerary_list"] = "itineraryList" in body
            done.set()

        page.on("response", lambda response: asyncio.create_task(capture_response(response)))
        navigation_error = ""
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        except Exception as exc:
            navigation_error = str(exc)[:300]

        try:
            await asyncio.wait_for(done.wait(), timeout=args.timeout)
        except asyncio.TimeoutError:
            captured["response_status"] = None
            captured["timeout"] = True

        selectors = [
            "form[action*='showfarefirst']",
            "form.flight-search-form",
            "input[placeholder*='From']",
            "input[placeholder*='Destination']",
            "button:has-text('Search')",
            "text=Search flights",
            "text=Search",
        ]
        selector_counts: dict[str, int] = {}
        for selector in selectors:
            try:
                selector_counts[selector] = await page.locator(selector).count()
            except Exception:
                selector_counts[selector] = -1

        html = ""
        try:
            html = await page.content()
        except Exception:
            pass
        regex_hits = {
            "FlightListSearch": bool(re.search("FlightListSearch", html)),
            "itineraryList": bool(re.search("itineraryList", html)),
            "flight-search-form": bool(re.search("flight-search-form", html)),
            "search-form": bool(re.search("search-form", html)),
        }

        try:
            await page.screenshot(path=str(screenshot_path), full_page=True)
        except Exception:
            screenshot_path = None

        await context.close()
        await browser.close()

    result = {
        "url": url,
        "date": args.date,
        "return_date": args.return_date,
        "response_seen": bool(captured.get("response_status")),
        "response_status": captured.get("response_status"),
        "response_body_length": captured.get("body_length"),
        "has_itinerary_list": captured.get("has_itinerary_list"),
        "timeout": bool(captured.get("timeout")),
        "navigation_error": navigation_error,
        "selector_counts": selector_counts,
        "regex_hits": regex_hits,
        "screenshot": str(screenshot_path) if screenshot_path else "",
    }
    (outdir / f"diagnose-{stamp}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result


def main() -> None:
    args = parse_args()
    result = asyncio.run(inspect_page(args))
    compact = {
        "response_status": result["response_status"],
        "has_itinerary_list": result["has_itinerary_list"],
        "timeout": result["timeout"],
        "screenshot": bool(result["screenshot"]),
    }
    print(json.dumps(compact, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": " ".join(str(exc).split())[:350]}, ensure_ascii=False))
        raise SystemExit(1)
