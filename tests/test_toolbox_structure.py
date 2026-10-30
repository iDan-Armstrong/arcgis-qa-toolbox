"""Structural checks on the .pyt without importing it.

CI has no arcpy, so the toolbox can't be imported here — but it can be
parsed. These tests catch the mistakes that otherwise only surface when
someone opens the toolbox in Pro: a tool missing from the Toolbox.tools
list, a tool class without execute/getParameterInfo, a syntax error.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

REPO = Path(__file__).parents[1]
PYT = REPO / "toolbox" / "QAToolbox.pyt"


@pytest.fixture(scope="module")
def tree() -> ast.Module:
    return ast.parse(PYT.read_text(), filename=str(PYT))


def classes(tree: ast.Module) -> dict[str, ast.ClassDef]:
    return {n.name: n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}


def methods(cls: ast.ClassDef) -> set[str]:
    return {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}


def test_pyt_parses(tree: ast.Module) -> None:
    assert tree is not None


def test_toolbox_class_exists_with_tools(tree: ast.Module) -> None:
    cls = classes(tree).get("Toolbox")
    assert cls is not None, "a .pyt must define a class named Toolbox"
    assert "__init__" in methods(cls)


def test_registered_tools_exist_and_are_complete(tree: ast.Module) -> None:
    source = PYT.read_text()
    all_classes = classes(tree)
    # every class assigned to self.tools must exist and implement the tool protocol
    toolbox = all_classes["Toolbox"]
    tool_names: list[str] = []
    for node in ast.walk(toolbox):
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Attribute)]
            if any(t.attr == "tools" for t in targets) and isinstance(node.value, ast.List):
                tool_names = [e.id for e in node.value.elts if isinstance(e, ast.Name)]
    assert tool_names, "Toolbox.tools is empty"
    for name in tool_names:
        assert name in all_classes, f"tool {name} referenced but not defined"
        tool_methods = methods(all_classes[name])
        for required in ("__init__", "getParameterInfo", "execute"):
            assert required in tool_methods, f"{name} missing {required}"
    assert "arcpy" in source  # sanity: it's really an arcpy toolbox


def test_example_rules_json_is_valid_for_engine() -> None:
    from qacore.rules import Rule

    config = json.loads((REPO / "examples" / "facility_rules.json").read_text())
    rules = [Rule.from_config(r) for r in config["rules"]]
    assert len(rules) == 5
    assert config["unique_fields"] == ["facility_id"]


def test_adapter_is_the_only_arcpy_import() -> None:
    """The architectural rule this repo exists to demonstrate, enforced by a test."""
    src = REPO / "src" / "qacore"
    for path in src.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            has_arcpy = (
                isinstance(node, ast.Import) and any(a.name == "arcpy" for a in node.names)
            ) or (isinstance(node, ast.ImportFrom) and node.module == "arcpy")
            if has_arcpy:
                assert path.name == "arcpy_adapter.py", f"arcpy imported in {path.name}"
                # and only inside a function, never at module level
                assert node.col_offset > 0, "arcpy must be imported lazily"
