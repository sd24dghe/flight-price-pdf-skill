#!/usr/bin/env python3
"""Offline tests for run_flight_pdf.py (no network, no Playwright required)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "flight-price" / "scripts"))

import run_flight_pdf as rfp  # noqa: E402


def meta_for(origins):
    return {
        "title": "t", "origins": origins, "dest": "MXP", "trip_type": "roundtrip",
        "stay": 7, "days": 8, "depart": "2026-03-01", "to": "2026-03-07",
        "generated": "2026-01-01 00:00", "currency": "CNY", "airlines": [],
        "n_queries": 7, "stats": {"ok": 7, "no_results": 0, "timeout": 0, "failed": 0},
        "retried": 0, "hint": None,
    }


class RunFlightPdfTest(unittest.TestCase):
    def test_nested_layout_sample(self) -> None:
        rows, _, stats = rfp.load_rows(ROOT / "examples" / "HKG-MXP-sample.json", "HKG")
        self.assertEqual(stats["ok"], 1)
        self.assertEqual(len({r["cur"] for r in rows}), 1)
        self.assertTrue(all(r["dep"] and r["price"] for r in rows))
        self.assertTrue(any(r["direct"] for r in rows))
        html = rfp.build_html(meta_for(["HKG"]), rows)
        self.assertIn("TOP 10", html)
        self.assertIn(f'¥{min(r["price"] for r in rows):.0f}', html)

    def test_flat_layout_from_real_scan(self) -> None:
        sample = ROOT / "examples" / "flat-scan-sample.json"
        rows, pairs, stats = rfp.load_rows(sample, "HKG")
        self.assertEqual(rows[0]["price"], 2135.0)
        self.assertEqual(rows[0]["air"], "UO")
        self.assertTrue(rows[0]["direct"])
        self.assertEqual(pairs, [])
        self.assertEqual(stats["ok"], 1)
        html = rfp.build_html(meta_for(["HKG"]), rows)
        self.assertIn("UO622", html)
        self.assertIn("直飞", html)

    def test_multi_origin_best_and_champ(self) -> None:
        flat = ROOT / "examples" / "flat-scan-sample.json"
        rows, _, _ = rfp.load_rows(flat, "HKG")
        cheap = dict(rows[0], org="MFM", price=1999.0, direct=False, stops=1)
        rows.append(cheap)
        html = rfp.build_html(meta_for(["HKG", "MFM"]), rows)
        self.assertIn("★最便宜", html)
        self.assertIn("中转1次", html)

    def test_retry_pairs_collected(self) -> None:
        # timeout results must surface as pairs for the single retry pass
        import json
        import tempfile
        data = {"results": [
            {"date": "2026-03-02", "return_date": "2026-03-09", "status": "timeout"},
            {"date": "2026-03-03", "return_date": "2026-03-10", "status": "ok",
             "options": [{"price": 100, "currency": "CNY", "flight_nos": ["CX1"],
                          "segments": []}]},
        ], "flights": []}
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.json"
            p.write_text(json.dumps(data), encoding="utf-8")
            rows, pairs, stats = rfp.load_rows(p, "XXX")
        self.assertEqual(pairs, [("2026-03-02", "2026-03-09")])
        self.assertEqual(stats["timeout"], 1)
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
