#!/usr/bin/env python3
"""Test natural-language trip mapping and generic wrapper arguments."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "flight-price" / "scripts"))

import run_flight_query  # noqa: E402


def base_args(**overrides):
    values = {
        "origin": "HKG",
        "dest": "MXP",
        "date_from": "2027-06-01",
        "date_to": "2027-06-30",
        "pairs": None,
        "trip_type": None,
        "rt": False,
        "stay": None,
        "days": None,
        "return_date": None,
        "direct": False,
        "max_stops": None,
        "airline": None,
        "exclude_airline": None,
        "depart_after": None,
        "depart_before": None,
        "limit": 20,
        "sort": "price",
        "cabin": "economy",
        "adults": 1,
        "currency": "CNY",
        "concurrency": 5,
        "cache": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class TripMappingTest(unittest.TestCase):
    def test_trip_type_aliases(self) -> None:
        self.assertEqual(run_flight_query.normalize_trip_type("往返"), "roundtrip")
        self.assertEqual(run_flight_query.normalize_trip_type("单程"), "oneway")
        self.assertEqual(run_flight_query.normalize_trip_type("RT"), "roundtrip")

    def test_days_become_nights(self) -> None:
        args = base_args(trip_type="roundtrip", days=8)
        self.assertEqual(run_flight_query.effective_stay(args), 7)
        command = run_flight_query.build_command(args, "flight-price")
        self.assertIn("--rt", command)
        stay_index = command.index("--stay")
        self.assertEqual(command[stay_index + 1], "7")

    def test_nights_stay_unchanged(self) -> None:
        args = base_args(trip_type="roundtrip", stay=8)
        self.assertEqual(run_flight_query.effective_stay(args), 8)

    def test_oneway_rejects_days_and_return(self) -> None:
        with self.assertRaises(ValueError):
            run_flight_query.build_command(
                base_args(trip_type="oneway", days=8),
                "flight-price",
            )
        with self.assertRaises(ValueError):
            run_flight_query.build_command(
                base_args(trip_type="oneway", return_date="2027-06-10"),
                "flight-price",
            )

    def test_pairs_reject_trip_type(self) -> None:
        with self.assertRaises(ValueError):
            run_flight_query.build_command(
                base_args(pairs="2027-06-01:2027-06-08", trip_type="roundtrip"),
                "flight-price",
            )


if __name__ == "__main__":
    unittest.main()
