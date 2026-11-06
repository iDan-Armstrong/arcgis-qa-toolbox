"""Build examples/qa_demo.gdb for trying the toolbox in ArcGIS Pro.

Run once in the ArcGIS Pro Python window or the Pro conda environment:

    python examples/make_demo_gdb.py

It writes two feature classes from demo_facilities.csv (synthetic data with
deliberate defects):

  facilities          matches facility_schema.json, but has bad records:
                      duplicate IDs, a missing name, a typo outside the type
                      domain, negative beds and malformed phone numbers.
                      Feature Class QA should fail on every rule.
  facilities_drifted  the same records with a drifted schema: beds stored as
                      Double, phone widened to 50 characters and an extra
                      district field. Schema Compare should report all three.

Re-running replaces the geodatabase.
"""

from __future__ import annotations

import csv
from pathlib import Path

import arcpy

HERE = Path(__file__).resolve().parent
GDB = HERE / "qa_demo.gdb"
CSV = HERE / "demo_facilities.csv"
WGS84 = arcpy.SpatialReference(4326)

# (name, type, length, nullable) for each feature class
FIELDS = {
    "facilities": [
        ("facility_id", "LONG", None, False),
        ("facility_name", "TEXT", 100, False),
        ("facility_type", "TEXT", 20, False),
        ("beds", "LONG", None, True),
        ("phone", "TEXT", 20, True),
    ],
    "facilities_drifted": [
        ("facility_id", "LONG", None, False),
        ("facility_name", "TEXT", 100, False),
        ("facility_type", "TEXT", 20, False),
        ("beds", "DOUBLE", None, True),
        ("phone", "TEXT", 50, True),
        ("district", "TEXT", 50, True),
    ],
}


def _blank_to_null(value: str) -> str | None:
    return value if value.strip() else None


def build() -> None:
    if arcpy.Exists(str(GDB)):
        arcpy.management.Delete(str(GDB))
    arcpy.management.CreateFileGDB(str(HERE), GDB.name)
    with CSV.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    for fc_name, fields in FIELDS.items():
        fc = arcpy.management.CreateFeatureclass(str(GDB), fc_name, "POINT",
                                                 spatial_reference=WGS84).getOutput(0)
        for name, ftype, length, nullable in fields:
            arcpy.management.AddField(
                fc, name, ftype, field_length=length,
                field_is_nullable="NULLABLE" if nullable else "NON_NULLABLE",
            )
        names = [f[0] for f in fields]
        with arcpy.da.InsertCursor(fc, ["SHAPE@XY", *names]) as cur:
            for r in rows:
                # A NOT NULL text field cannot hold a null, so the missing name
                # is stored as an empty string; the QA rules treat both as blank.
                values = {
                    "facility_id": int(r["facility_id"]),
                    "facility_name": r["facility_name"] or "",
                    "facility_type": r["facility_type"] or "",
                    "beds": int(r["beds"]),
                    "phone": _blank_to_null(r["phone"]),
                    "district": None,
                }
                cur.insertRow([(float(r["lon"]), float(r["lat"])), *(values[n] for n in names)])
        print(f"{fc_name}: {len(rows)} features")
    print(f"Wrote {GDB}")


if __name__ == "__main__":
    build()
