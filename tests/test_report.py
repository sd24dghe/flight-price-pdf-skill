#!/usr/bin/env python3
"""Smoke tests for the sanitized HKG-MXP example."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = ROOT / "flight-price" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

import flight_report  # noqa: E402


class FlightReportTest(unittest.TestCase):
    def test_sample_generates_all_formats(self) -> None:
        sample_path = ROOT / "examples" / "HKG-MXP-sample.json"
        data = json.loads(sample_path.read_text(encoding="utf-8"))
        rows = flight_report.collect_candidates(data)

        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["price"], 4160.0)
        self.assertIn("直飞", flight_report.build_pdf_advice(rows))
        self.assertEqual(rows[0]["price_basis"], "含税总价")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            pdf = temp / "sample.pdf"
            xlsx = temp / "sample.xlsx"
            docx = temp / "sample.docx"

            flight_report.write_pdf(
                pdf,
                rows,
                data,
                4,
                "HKG-MXP 测试汇总",
                "Trip.com / flight-price",
                "https://tw.trip.com/chinaflights/",
            )
            flight_report.write_xlsx(
                xlsx,
                rows,
                data,
                4,
                "HKG-MXP 测试汇总",
                "Trip.com / flight-price",
                "https://tw.trip.com/chinaflights/",
            )
            flight_report.write_docx(
                docx,
                rows,
                data,
                4,
                "HKG-MXP 测试汇总",
                "Trip.com / flight-price",
                "https://tw.trip.com/chinaflights/",
            )

            self.assertGreater(pdf.stat().st_size, 1000)
            self.assertGreater(xlsx.stat().st_size, 1000)
            self.assertGreater(docx.stat().st_size, 1000)
            text = "\n".join(
                (page.extract_text() or "")
                for page in PdfReader(str(pdf)).pages
            )
            self.assertIn("仅比价、不出票", text)
            self.assertIn("含税总价", text)
            self.assertIn("第 3 名是直飞", text)


if __name__ == "__main__":
    unittest.main()
