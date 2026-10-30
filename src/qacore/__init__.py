"""qacore: the arcpy-free heart of the QA toolbox.

Everything here operates on plain Python records (``list[dict]``) and plain
schema descriptions, so it runs — and is tested — anywhere. The .pyt and the
GP service are thin arcpy adapters that feed cursors in and selections out.

Why this split matters:
- CI has no ArcGIS license, but the business logic still gets full test coverage.
- The same rules run in ArcGIS Pro, as a GP service, and in a plain cron job.
- arcpy imports cost seconds; developers iterating on rules pay nothing.
"""

from qacore.rules import Rule, RuleResult, RunSummary, run_rules
from qacore.schema import FieldSpec, SchemaDiff, compare_schema

__all__ = [
    "FieldSpec",
    "Rule",
    "RuleResult",
    "RunSummary",
    "SchemaDiff",
    "compare_schema",
    "run_rules",
]

__version__ = "0.2.0"
