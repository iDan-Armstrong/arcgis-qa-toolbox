"""The only module that touches arcpy. Imported lazily so qacore works anywhere.

Adapter responsibilities, nothing more:
- feature class -> (oid, record) tuples for the rule engine
- feature class -> list[FieldSpec] for schema comparison
- RunSummary -> selection layer / messages back in ArcGIS
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from qacore.rules import Record, RunSummary
from qacore.schema import FieldSpec

# Esri field type -> contract type vocabulary
_TYPE_MAP = {
    "OID": "Integer",
    "Integer": "Integer",
    "SmallInteger": "Integer",
    "BigInteger": "Integer",
    "Double": "Double",
    "Single": "Double",
    "String": "String",
    "Date": "Date",
    "DateOnly": "Date",
    "GlobalID": "GlobalID",
    "Guid": "Guid",
    "Geometry": "Geometry",
}


def iter_records(fc: str, fields: list[str]) -> Iterator[tuple[int, Record]]:
    """Stream (oid, record) tuples from a feature class — one cursor pass."""
    import arcpy

    oid_field = arcpy.Describe(fc).OIDFieldName
    cursor_fields = [oid_field, *fields]
    with arcpy.da.SearchCursor(fc, cursor_fields) as cursor:
        for row in cursor:
            yield int(row[0]), dict(zip(fields, row[1:]))


def describe_fields(fc: str) -> list[FieldSpec]:
    import arcpy

    specs = []
    for f in arcpy.ListFields(fc):
        specs.append(
            FieldSpec(
                name=f.name,
                type=_TYPE_MAP.get(f.type, f.type),
                length=f.length if f.type == "String" else None,
                nullable=f.isNullable,
            )
        )
    return specs


def select_failures(fc: str, summary: RunSummary, layer_name: str = "qa_failures") -> Any:
    """Make a layer selecting the failing OIDs, for immediate review in Pro."""
    import arcpy

    oids = sorted(summary.failing_oids)
    layer = arcpy.management.MakeFeatureLayer(fc, layer_name).getOutput(0)
    if oids:
        oid_field = arcpy.Describe(fc).OIDFieldName
        where = f"{oid_field} IN ({', '.join(map(str, oids))})"
        arcpy.management.SelectLayerByAttribute(layer, "NEW_SELECTION", where)
    return layer


def log_summary(summary: RunSummary) -> None:
    import arcpy

    for line in summary.to_lines():
        (arcpy.AddWarning if "FAIL" in line else arcpy.AddMessage)(line)
