"""
Tests for the neuro-symbolic predicate decomposer.

Verifies:
- Rules load correctly from YAML
- Each predicate type evaluates as expected
- Custom predicates fall back correctly
- Unknown task types return no predicates
- File paths work cross-platform (Windows-safe)
"""

import tempfile
from pathlib import Path

from app.predicate_decomposer import (
    Predicate,
    PredicateDecomposer,
    PredicateType,
)


def _write_rules_yaml(artifact_path: str = "") -> Path:
    """Write a temporary verification_rules.yaml and return its path."""
    content = f"""
version: "1.0.0"
verification_rules:
  code_modification:
    predicates:
      - name: "target_file_exists"
        type: "artifact_exists"
        params: {{path: "{artifact_path}"}}
        description: "File must exist"
      - name: "no_error_in_final"
        type: "no_error_in_final"
        description: "No error in final event"
      - name: "cost_within_budget"
        type: "cost_within_budget"
        params: {{max_cents: 100.0}}
        description: "Cost must be under 100c"
  data_analysis:
    predicates:
      - name: "output_exists"
        type: "artifact_exists"
        params: {{path: "{artifact_path}"}}
"""
    tmpdir = Path(tempfile.mkdtemp())
    path = tmpdir / "verification_rules.yaml"
    path.write_text(content)
    return path


def test_decomposer_loads_rules_for_known_task():
    path = _write_rules_yaml("/tmp/x.txt")
    d = PredicateDecomposer(rules_path=str(path))
    predicates = d.decompose("code_modification", {})
    assert len(predicates) == 3
    names = [p.name for p in predicates]
    assert "target_file_exists" in names
    assert "no_error_in_final" in names
    assert "cost_within_budget" in names


def test_decomposer_returns_empty_for_unknown_task():
    path = _write_rules_yaml("/tmp/x.txt")
    d = PredicateDecomposer(rules_path=str(path))
    predicates = d.decompose("does_not_exist", {})
    assert predicates == []


def test_predicate_types_parse_from_yaml():
    path = _write_rules_yaml("/tmp/x.txt")
    d = PredicateDecomposer(rules_path=str(path))
    predicates = d.decompose("code_modification", {})
    types = {p.name: p.predicate_type for p in predicates}
    assert types["target_file_exists"] == PredicateType.ARTIFACT_EXISTS
    assert types["no_error_in_final"] == PredicateType.NO_ERROR_IN_FINAL
    assert types["cost_within_budget"] == PredicateType.COST_WITHIN_BUDGET


def test_artifact_exists_passes_when_file_present():
    with tempfile.TemporaryDirectory() as tmp:
        real_file = Path(tmp) / "output.txt"
        real_file.write_text("content")
        path = _write_rules_yaml(real_file.as_posix())
        d = PredicateDecomposer(rules_path=str(path))
        predicates = d.decompose("code_modification", {})
        target = next(p for p in predicates if p.name == "target_file_exists")
        result = d.evaluate(target, {})
        assert result.passed is True
        assert "exists" in result.detail.lower()


def test_artifact_exists_fails_when_file_missing():
    path = _write_rules_yaml("/definitely/not/a/real/path.txt")
    d = PredicateDecomposer(rules_path=str(path))
    predicates = d.decompose("code_modification", {})
    target = next(p for p in predicates if p.name == "target_file_exists")
    result = d.evaluate(target, {})
    assert result.passed is False
    assert "missing" in result.detail.lower()


def test_no_error_in_final_passes_when_no_error():
    path = _write_rules_yaml("/tmp/x.txt")
    d = PredicateDecomposer(rules_path=str(path))
    predicates = d.decompose("code_modification", {})
    target = next(p for p in predicates if p.name == "no_error_in_final")
    result = d.evaluate(target, {"final_error": None})
    assert result.passed is True


def test_no_error_in_final_fails_when_error_present():
    path = _write_rules_yaml("/tmp/x.txt")
    d = PredicateDecomposer(rules_path=str(path))
    predicates = d.decompose("code_modification", {})
    target = next(p for p in predicates if p.name == "no_error_in_final")
    result = d.evaluate(target, {"final_error": "timeout occurred"})
    assert result.passed is False
    assert "timeout" in result.detail


def test_cost_within_budget_passes_under_limit():
    path = _write_rules_yaml("/tmp/x.txt")
    d = PredicateDecomposer(rules_path=str(path))
    predicates = d.decompose("code_modification", {})
    target = next(p for p in predicates if p.name == "cost_within_budget")
    result = d.evaluate(target, {"cost_cents": 50.0})
    assert result.passed is True


def test_cost_within_budget_fails_over_limit():
    path = _write_rules_yaml("/tmp/x.txt")
    d = PredicateDecomposer(rules_path=str(path))
    predicates = d.decompose("code_modification", {})
    target = next(p for p in predicates if p.name == "cost_within_budget")
    result = d.evaluate(target, {"cost_cents": 150.0})
    assert result.passed is False


def test_custom_predicate_uses_injected_evaluator():
    path = _write_rules_yaml("/tmp/x.txt")
    d = PredicateDecomposer(rules_path=str(path))
    custom = Predicate(
        name="custom_check",
        predicate_type=PredicateType.CUSTOM,
        params={},
        description="",
    )

    def evaluator(pred, ctx):
        return (True, "custom evaluator approved")

    result = d.evaluate(custom, {"_custom_evaluator": evaluator})
    assert result.passed is True
    assert "custom evaluator" in result.detail


def test_custom_predicate_without_evaluator_fails_safe():
    path = _write_rules_yaml("/tmp/x.txt")
    d = PredicateDecomposer(rules_path=str(path))
    custom = Predicate(
        name="custom_check",
        predicate_type=PredicateType.CUSTOM,
        params={},
        description="",
    )
    result = d.evaluate(custom, {})
    assert result.passed is False
    assert "no evaluator" in result.detail.lower()