from __future__ import annotations

import json
from pathlib import Path

from qacore.schema import FieldSpec, compare_schema, load_contract

EXPECTED = [
    FieldSpec("facility_id", "Integer", nullable=False),
    FieldSpec("facility_name", "String", length=100, nullable=False),
    FieldSpec("beds", "Integer"),
]


def actual(*overrides: FieldSpec) -> list[FieldSpec]:
    base = {
        "OBJECTID": FieldSpec("OBJECTID", "Integer", nullable=False),
        "Shape": FieldSpec("Shape", "Geometry"),
        "facility_id": FieldSpec("facility_id", "Integer", nullable=False),
        "facility_name": FieldSpec("facility_name", "String", length=100, nullable=False),
        "beds": FieldSpec("beds", "Integer"),
    }
    for o in overrides:
        base[o.name] = o
    return list(base.values())


def test_clean_schema_ignores_system_fields() -> None:
    diff = compare_schema(EXPECTED, actual())
    assert diff.clean
    assert diff.to_lines() == ["schema: OK"]


def test_missing_field() -> None:
    fields = [f for f in actual() if f.name != "beds"]
    diff = compare_schema(EXPECTED, fields)
    assert [f.name for f in diff.missing] == ["beds"]


def test_unexpected_field_and_allow_extra() -> None:
    fields = actual(FieldSpec("legacy_code", "String", length=10))
    assert compare_schema(EXPECTED, fields).unexpected == ["legacy_code"]
    assert compare_schema(EXPECTED, fields, allow_extra=True).clean


def test_type_length_nullable_mismatches() -> None:
    fields = actual(FieldSpec("facility_name", "String", length=50, nullable=True))
    diff = compare_schema(EXPECTED, fields)
    assert len(diff.mismatched) == 1
    expected, got = diff.mismatched[0]
    assert expected.length == 100 and got.length == 50
    assert "mismatch on facility_name" in "\n".join(diff.to_lines())


def test_name_matching_is_case_insensitive() -> None:
    fields = actual(FieldSpec("FACILITY_ID", "Integer", nullable=False))
    fields = [f for f in fields if f.name != "facility_id"]
    assert compare_schema(EXPECTED, fields).clean


def test_load_contract_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "contract.json"
    path.write_text(
        json.dumps({"fields": [{"name": "a", "type": "Integer", "nullable": False}]})
    )
    specs = load_contract(path)
    assert specs == [FieldSpec("a", "Integer", nullable=False)]


def test_example_contract_parses() -> None:
    specs = load_contract(Path(__file__).parents[1] / "examples" / "facility_schema.json")
    assert {s.name for s in specs} >= {"facility_id", "facility_name", "facility_type"}
