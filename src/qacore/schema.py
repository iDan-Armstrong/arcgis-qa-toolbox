"""Schema contracts: declare the fields a dataset must have, diff reality against it.

A contract is JSON (checked into the project repo, reviewed like code):

    {"fields": [
        {"name": "facility_id", "type": "Integer", "nullable": false},
        {"name": "facility_name", "type": "String", "length": 100}
    ]}

The adapter describes the live feature class and we diff. This is how schema
drift gets caught *before* a nightly load fails at 2 a.m.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: str
    length: int | None = None
    nullable: bool = True

    @classmethod
    def from_dict(cls, raw: dict) -> FieldSpec:
        return cls(
            name=raw["name"],
            type=raw["type"],
            length=raw.get("length"),
            nullable=raw.get("nullable", True),
        )


@dataclass
class SchemaDiff:
    missing: list[FieldSpec]
    unexpected: list[str]
    mismatched: list[tuple[FieldSpec, FieldSpec]]  # (expected, actual)

    @property
    def clean(self) -> bool:
        return not (self.missing or self.unexpected or self.mismatched)

    def to_lines(self) -> list[str]:
        if self.clean:
            return ["schema: OK"]
        lines = ["schema: DRIFT DETECTED"]
        for f in self.missing:
            lines.append(f"  missing field: {f.name} ({f.type})")
        for name in self.unexpected:
            lines.append(f"  unexpected field: {name}")
        for expected, actual in self.mismatched:
            lines.append(
                f"  mismatch on {expected.name}: expected {expected.type}"
                f"(len={expected.length}, nullable={expected.nullable}), "
                f"got {actual.type}(len={actual.length}, nullable={actual.nullable})"
            )
        return lines


def load_contract(path: str | Path) -> list[FieldSpec]:
    raw = json.loads(Path(path).read_text())
    return [FieldSpec.from_dict(f) for f in raw["fields"]]


def compare_schema(
    expected: list[FieldSpec],
    actual: list[FieldSpec],
    ignore: set[str] | None = None,
    allow_extra: bool = False,
) -> SchemaDiff:
    """Diff expected vs actual fields.

    ``ignore`` defaults to the system fields every geodatabase adds
    (OBJECTID, Shape, etc.) so contracts stay about *your* data model.
    """
    ignore = {s.lower() for s in (ignore or {"objectid", "shape", "shape_length", "shape_area",
                                             "globalid", "created_user", "created_date",
                                             "last_edited_user", "last_edited_date"})}
    actual_by_name = {f.name.lower(): f for f in actual if f.name.lower() not in ignore}
    expected_by_name = {f.name.lower(): f for f in expected}

    missing = [f for key, f in expected_by_name.items() if key not in actual_by_name]
    unexpected = (
        [] if allow_extra
        else [f.name for key, f in actual_by_name.items() if key not in expected_by_name]
    )

    mismatched = []
    for key, exp in expected_by_name.items():
        act = actual_by_name.get(key)
        if act is None:
            continue
        type_ok = exp.type.lower() == act.type.lower()
        length_ok = exp.length is None or exp.length == act.length
        nullable_ok = exp.nullable or not act.nullable
        if not (type_ok and length_ok and nullable_ok):
            mismatched.append((exp, act))

    return SchemaDiff(missing=missing, unexpected=sorted(unexpected), mismatched=mismatched)
