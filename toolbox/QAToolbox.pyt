# -*- coding: utf-8 -*-
"""QA Toolbox: ArcGIS Pro Python Toolbox wrapping the tested qacore engine.

Install: pip install -e . into the active Pro conda environment (or add src/
to the Python path), then add this .pyt to a project.

The tools stay deliberately thin — parameter plumbing only. All logic lives
in qacore, where it has unit tests that run in CI without an ArcGIS license.
"""

import json

import arcpy

from qacore.arcpy_adapter import describe_fields, iter_records, log_summary, select_failures
from qacore.rules import Rule, run_rules
from qacore.schema import compare_schema, load_contract


class Toolbox:
    def __init__(self):
        self.label = "QA Toolbox"
        self.alias = "qatoolbox"
        self.tools = [FeatureClassQA, SchemaCompare]


class FeatureClassQA:
    """Run a JSON rule file against a feature class; select failing features."""

    def __init__(self):
        self.label = "Feature Class QA"
        self.description = (
            "Evaluates declarative QA rules (not-null, domain, range, regex, "
            "uniqueness) against a feature class in a single cursor pass and "
            "returns a layer with failing features selected."
        )
        self.canRunInBackground = True

    def getParameterInfo(self):
        fc = arcpy.Parameter(
            displayName="Input Features",
            name="in_features",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input",
        )
        rules = arcpy.Parameter(
            displayName="Rules File (JSON)",
            name="rules_file",
            datatype="DEFile",
            parameterType="Required",
            direction="Input",
        )
        rules.filter.list = ["json"]
        fail_on_error = arcpy.Parameter(
            displayName="Fail the tool if any rule fails",
            name="fail_on_error",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
        )
        fail_on_error.value = False
        out_layer = arcpy.Parameter(
            displayName="Failures Layer",
            name="out_layer",
            datatype="GPFeatureLayer",
            parameterType="Derived",
            direction="Output",
        )
        return [fc, rules, fail_on_error, out_layer]

    def execute(self, parameters, messages):
        fc = parameters[0].valueAsText
        rules_path = parameters[1].valueAsText
        fail_on_error = bool(parameters[2].value)

        config = json.loads(open(rules_path).read())
        rules = [Rule.from_config(r) for r in config.get("rules", [])]
        unique_fields = config.get("unique_fields", [])

        # read only the fields the rules need — cursors over wide tables are slow
        needed = set(unique_fields)
        for rule in rules:
            params = rule.params
            needed.update(params.get("fields", []))
            if "field" in params:
                needed.add(params["field"])

        summary = run_rules(iter_records(fc, sorted(needed)), rules, unique_fields)
        log_summary(summary)

        layer = select_failures(fc, summary)
        parameters[3].value = layer

        if fail_on_error and not summary.passed:
            raise arcpy.ExecuteError(
                f"QA failed: {len(summary.failing_oids)} of {summary.total} features"
            )


class SchemaCompare:
    """Diff a feature class against a JSON schema contract; fail on drift."""

    def __init__(self):
        self.label = "Schema Compare"
        self.description = (
            "Compares a feature class schema against a versioned JSON contract "
            "and reports missing, unexpected, and mismatched fields."
        )
        self.canRunInBackground = True

    def getParameterInfo(self):
        fc = arcpy.Parameter(
            displayName="Input Features",
            name="in_features",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input",
        )
        contract = arcpy.Parameter(
            displayName="Schema Contract (JSON)",
            name="contract_file",
            datatype="DEFile",
            parameterType="Required",
            direction="Input",
        )
        contract.filter.list = ["json"]
        allow_extra = arcpy.Parameter(
            displayName="Allow extra fields",
            name="allow_extra",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
        )
        allow_extra.value = False
        clean = arcpy.Parameter(
            displayName="Schema is clean",
            name="is_clean",
            datatype="GPBoolean",
            parameterType="Derived",
            direction="Output",
        )
        return [fc, contract, allow_extra, clean]

    def execute(self, parameters, messages):
        fc = parameters[0].valueAsText
        expected = load_contract(parameters[1].valueAsText)
        allow_extra = bool(parameters[2].value)

        diff = compare_schema(expected, describe_fields(fc), allow_extra=allow_extra)
        for line in diff.to_lines():
            (arcpy.AddMessage if diff.clean else arcpy.AddWarning)(line)
        parameters[3].value = diff.clean
        if not diff.clean:
            raise arcpy.ExecuteError("schema drift detected — see messages")
