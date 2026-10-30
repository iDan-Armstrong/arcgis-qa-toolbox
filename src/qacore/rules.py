"""Record-level QA rules over plain dict records keyed by object ID.

The adapter (``.pyt`` / GP service) is responsible for turning a feature
class into ``records``: an iterable of ``(oid, {field: value})``. That is the
entire contract — nothing Esri-shaped crosses this boundary.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

Record = dict[str, Any]
Evaluator = Callable[..., Callable[[Record], bool]]
_EVALUATORS: dict[str, Evaluator] = {}


def _register(kind: str) -> Callable[[Evaluator], Evaluator]:
    def deco(fn: Evaluator) -> Evaluator:
        _EVALUATORS[kind] = fn
        return fn

    return deco


@dataclass(frozen=True)
class Rule:
    """One declarative rule; ``kind`` picks the evaluator, params configure it."""

    kind: str
    params: dict[str, Any] = field(default_factory=dict)
    label: str | None = None

    @classmethod
    def from_config(cls, raw: dict[str, Any]) -> Rule:
        raw = dict(raw)
        kind = raw.pop("kind", None)
        if kind not in _EVALUATORS:
            raise ValueError(f"unknown rule kind {kind!r}; available: {sorted(_EVALUATORS)}")
        return cls(kind=kind, params=raw.pop("params", raw), label=raw.get("label"))

    def describe(self) -> str:
        return self.label or f"{self.kind}({self.params})"


@dataclass
class RuleResult:
    rule: Rule
    failing_oids: list[int] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failing_oids


@dataclass
class RunSummary:
    total: int
    results: list[RuleResult]

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def failing_oids(self) -> set[int]:
        out: set[int] = set()
        for r in self.results:
            out.update(r.failing_oids)
        return out

    def to_lines(self) -> list[str]:
        """Plain-text report, suitable for arcpy.AddMessage line by line."""
        lines = [
            f"QA: {self.total} features checked — "
            + ("PASS" if self.passed else f"FAIL ({len(self.failing_oids)} features)")
        ]
        for r in self.results:
            status = "pass" if r.passed else f"FAIL ({len(r.failing_oids)})"
            lines.append(f"  [{status}] {r.rule.describe()}")
            if r.failing_oids:
                shown = ", ".join(map(str, sorted(r.failing_oids)[:20]))
                more = len(r.failing_oids) - 20
                lines.append(f"    OIDs: {shown}" + (f" … +{more} more" if more > 0 else ""))
        return lines


# --- evaluators: each returns a predicate 'record fails this rule?' ---


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


@_register("not_null")
def _not_null(fields: list[str]) -> Callable[[Record], bool]:
    return lambda rec: any(_is_blank(rec.get(f)) for f in fields)


@_register("in_set")
def _in_set(field: str, values: list[Any]) -> Callable[[Record], bool]:
    allowed = set(values)
    return lambda rec: rec.get(field) not in allowed


@_register("range")
def _range(
    field: str,
    min: float | None = None,  # noqa: A002 - config-facing name
    max: float | None = None,  # noqa: A002
) -> Callable[[Record], bool]:
    def fails(rec: Record) -> bool:
        value = rec.get(field)
        if value is None:
            return True
        try:
            value = float(value)
        except (TypeError, ValueError):
            return True
        return (min is not None and value < min) or (max is not None and value > max)

    return fails


@_register("regex")
def _regex(field: str, pattern: str) -> Callable[[Record], bool]:
    import re

    compiled = re.compile(pattern)
    return lambda rec: not isinstance(rec.get(field), str) or not compiled.fullmatch(rec[field])


@_register("min_length")
def _min_length(field: str, length: int) -> Callable[[Record], bool]:
    return lambda rec: _is_blank(rec.get(field)) or len(str(rec[field]).strip()) < length


def run_rules(
    records: Iterable[tuple[int, Record]],
    rules: list[Rule],
    unique_fields: list[str] | None = None,
) -> RunSummary:
    """Evaluate all rules in a single pass over the records.

    Single-pass matters: feature classes come through cursors, and a
    million-row layer should be read once, not once per rule. Uniqueness is
    handled here (not as a per-record rule) because it needs cross-record
    state.
    """
    predicates = [(rule, _EVALUATORS[rule.kind](**rule.params)) for rule in rules]
    results = {id(rule): RuleResult(rule=rule) for rule, _ in predicates}

    unique_fields = unique_fields or []
    seen: dict[str, dict[Any, int]] = {f: {} for f in unique_fields}
    dup_results = {
        f: RuleResult(rule=Rule(kind="unique", params={"field": f})) for f in unique_fields
    }

    total = 0
    for oid, rec in records:
        total += 1
        for rule, fails in predicates:
            if fails(rec):
                results[id(rule)].failing_oids.append(oid)
        for f in unique_fields:
            value = rec.get(f)
            if value in seen[f]:
                first = seen[f][value]
                if first not in dup_results[f].failing_oids:
                    dup_results[f].failing_oids.append(first)
                dup_results[f].failing_oids.append(oid)
            else:
                seen[f][value] = oid

    ordered = [results[id(rule)] for rule, _ in predicates]
    ordered += [dup_results[f] for f in unique_fields]
    return RunSummary(total=total, results=ordered)
