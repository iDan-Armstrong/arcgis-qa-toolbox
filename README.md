# arcgis-qa-toolbox — tested QA tools for ArcGIS Pro & Enterprise

![CI](https://github.com/iDan-Armstrong/arcgis-qa-toolbox/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/badge/license-MIT-green)

An ArcGIS Pro **Python Toolbox** (`.pyt`) and **geoprocessing service** for data QA,
built on an **arcpy-free core** so the logic is unit-tested in CI — no ArcGIS license
on the build machine required.

## The tools

| Tool | What it does |
|---|---|
| **Feature Class QA** | Evaluates a JSON rule file (not-null, domain, range, regex, min-length, uniqueness) against a feature class in a *single cursor pass* and returns the input with failing features selected. Optional hard-fail mode for use in automated chains. |
| **Schema Compare** | Diffs a feature class against a versioned JSON schema contract; reports missing / unexpected / mismatched fields and fails on drift. Catches the schema change *before* the nightly load does. |

Rules are data, reviewed like code:

```json
{
  "unique_fields": ["facility_id"],
  "rules": [
    { "kind": "not_null", "fields": ["facility_name", "facility_type"] },
    { "kind": "in_set", "field": "facility_type", "values": ["clinic", "hospital"] },
    { "kind": "range", "field": "beds", "min": 0, "max": 500 }
  ]
}
```

## Architecture: the arcpy boundary

```
src/qacore/            pure Python — fully unit tested, zero dependencies
  rules.py             single-pass rule engine over (oid, record) tuples
  schema.py            schema contracts + drift detection
  arcpy_adapter.py     the ONLY module that touches arcpy (lazily)
toolbox/QAToolbox.pyt  parameter plumbing only — logic-free by design
gp_service/            scripted draft -> stage -> publish to Enterprise
```

Why: arcpy is unavailable in CI, slow to import, and impossible to unit-test around.
Pinning it behind one adapter means the rule engine runs identically in ArcGIS Pro,
as a GP service, and in a plain scheduled script — and `tests/test_toolbox_structure.py`
**enforces the boundary with an AST check** (any arcpy import outside the adapter fails
the build). The `.pyt` itself can't be imported without Pro, but it *can* be parsed:
CI validates its structure (Toolbox class, registered tools, required methods) the same way.

## Use in ArcGIS Pro

Add `toolbox/QAToolbox.pyt` in Catalog. It uses the `qacore` package next to it, so
nothing needs installing into Pro's read-only default environment. (If you work in a
cloned environment, `pip install -e .` there takes precedence.)

**Feature Class QA** adds a `qa_failures` layer that holds only the failing features
(the OIDs go in its definition query), and the messages carry the per-rule report.
**Schema Compare** fails the tool with a plain error when the schema has drifted.

### Try it on demo data

```python
# in the ArcGIS Pro Python window
import runpy; runpy.run_path(r"<repo>\examples\make_demo_gdb.py", run_name="__main__")
```

This builds `examples/qa_demo.gdb` from the synthetic `demo_facilities.csv`:
`facilities` has bad records (Feature Class QA fails 12 of 201), and
`facilities_drifted` has a changed schema (Schema Compare reports three drifts).
Run against `facilities`, Schema Compare passes.

## Publish as a geoprocessing service

```bash
python gp_service/publish_gp_service.py \
    --portal https://portal.example.com/portal \
    --server https://server.example.com/server \
    --fc path/to/staging.gdb/facilities \
    --rules examples/facility_rules.json
```

Scripted `CreateGPSDDraft → StageService → UploadServiceDefinition`, failing loudly on
analyzer errors. Credentials come from `PORTAL_USER`/`PORTAL_PASSWORD` or the active Pro
sign-in — never from arguments or source.

## Develop

```bash
pip install -e ".[dev]"
pytest        # 21 tests, no ArcGIS required
ruff check .
```

## License

MIT
