from __future__ import annotations

import pytest

from qacore.rules import Rule, run_rules

RECORDS = [
    (1, {"facility_id": 100, "facility_name": "Alpha Clinic", "facility_type": "clinic",
         "beds": 12, "phone": "+1 555-0100"}),
    (2, {"facility_id": 101, "facility_name": "  ", "facility_type": "hospital",
         "beds": 250, "phone": "555-0101"}),
    (3, {"facility_id": 101, "facility_name": "Charlie Post", "facility_type": "spaceport",
         "beds": -5, "phone": "n/a"}),
    (4, {"facility_id": 103, "facility_name": "Dx", "facility_type": "pharmacy",
         "beds": None, "phone": None}),
]


def rules_from(*raw: dict) -> list[Rule]:
    return [Rule.from_config(dict(r)) for r in raw]


def test_unknown_kind_raises() -> None:
    with pytest.raises(ValueError, match="unknown rule kind"):
        Rule.from_config({"kind": "vibes"})


def test_not_null_blank_strings_count() -> None:
    summary = run_rules(RECORDS, rules_from({"kind": "not_null", "fields": ["facility_name"]}))
    assert summary.results[0].failing_oids == [2]


def test_in_set() -> None:
    summary = run_rules(
        RECORDS,
        rules_from({"kind": "in_set", "field": "facility_type",
                    "values": ["clinic", "hospital", "health_post", "pharmacy"]}),
    )
    assert summary.results[0].failing_oids == [3]


def test_range_null_and_nonnumeric_fail() -> None:
    summary = run_rules(
        RECORDS, rules_from({"kind": "range", "field": "beds", "min": 0, "max": 500})
    )
    assert summary.results[0].failing_oids == [3, 4]


def test_regex() -> None:
    summary = run_rules(
        RECORDS, rules_from({"kind": "regex", "field": "phone", "pattern": r"\+?[0-9\- ]{7,20}"})
    )
    assert summary.results[0].failing_oids == [3, 4]


def test_min_length() -> None:
    summary = run_rules(
        RECORDS, rules_from({"kind": "min_length", "field": "facility_name", "length": 3})
    )
    assert summary.results[0].failing_oids == [2, 4]


def test_uniqueness_flags_all_duplicates_including_first() -> None:
    summary = run_rules(RECORDS, [], unique_fields=["facility_id"])
    assert summary.results[-1].failing_oids == [2, 3]


def test_single_pass_aggregation_and_report() -> None:
    summary = run_rules(
        RECORDS,
        rules_from(
            {"kind": "not_null", "fields": ["facility_name"]},
            {"kind": "range", "field": "beds", "min": 0},
        ),
        unique_fields=["facility_id"],
    )
    assert summary.total == 4
    assert summary.failing_oids == {2, 3, 4}
    text = "\n".join(summary.to_lines())
    assert "FAIL" in text and "OIDs:" in text


def test_all_pass() -> None:
    clean = [(1, {"name": "A"}), (2, {"name": "B"})]
    summary = run_rules(clean, rules_from({"kind": "not_null", "fields": ["name"]}))
    assert summary.passed
    assert summary.to_lines()[0].endswith("PASS")
