"""
Tests for the formal logic combiner.

Verifies:
- Each operator (AND, OR, NOT, IMPLIES) computes correctly
- Nested formulas evaluate correctly
- The proof string is human-readable
- A failing predicate fails the AND formula
"""

from app.formal_combiner import (
    Formula,
    Operator,
    build_proof,
    evaluate_formula,
)


def test_and_all_true():
    formula = Formula(Operator.AND, ["a", "b", "c"])
    assert evaluate_formula(formula, {"a": True, "b": True, "c": True}) is True


def test_and_one_false():
    formula = Formula(Operator.AND, ["a", "b", "c"])
    assert evaluate_formula(formula, {"a": True, "b": False, "c": True}) is False


def test_or_all_false():
    formula = Formula(Operator.OR, ["a", "b", "c"])
    assert evaluate_formula(formula, {"a": False, "b": False, "c": False}) is False


def test_or_one_true():
    formula = Formula(Operator.OR, ["a", "b", "c"])
    assert evaluate_formula(formula, {"a": False, "b": True, "c": False}) is True


def test_not_inverts_true():
    formula = Formula(Operator.NOT, ["a"])
    assert evaluate_formula(formula, {"a": True}) is False


def test_not_inverts_false():
    formula = Formula(Operator.NOT, ["a"])
    assert evaluate_formula(formula, {"a": False}) is True


def test_implies_true_when_antecedent_false():
    """P -> Q is true whenever P is false (vacuous truth)."""
    formula = Formula(Operator.IMPLIES, ["a", "b"])
    assert evaluate_formula(formula, {"a": False, "b": False}) is True


def test_implies_false_when_antecedent_true_consequent_false():
    formula = Formula(Operator.IMPLIES, ["a", "b"])
    assert evaluate_formula(formula, {"a": True, "b": False}) is False


def test_implies_true_when_both_true():
    formula = Formula(Operator.IMPLIES, ["a", "b"])
    assert evaluate_formula(formula, {"a": True, "b": True}) is True


def test_nested_formula_and_of_or():
    """(a OR b) AND c"""
    formula = Formula(Operator.AND, [
        Formula(Operator.OR, ["a", "b"]),
        "c",
    ])
    assert evaluate_formula(formula, {"a": True, "b": False, "c": True}) is True
    assert evaluate_formula(formula, {"a": False, "b": False, "c": True}) is False


def test_nested_formula_or_of_and():
    """(a AND b) OR c"""
    formula = Formula(Operator.OR, [
        Formula(Operator.AND, ["a", "b"]),
        "c",
    ])
    assert evaluate_formula(formula, {"a": True, "b": True, "c": False}) is True
    assert evaluate_formula(formula, {"a": False, "b": True, "c": False}) is False
    assert evaluate_formula(formula, {"a": False, "b": False, "c": True}) is True


def test_failing_predicate_fails_and_formula():
    """The integration case: one failed predicate should fail the whole AND."""
    formula = Formula(Operator.AND, ["artifact", "no_error", "cost"])
    results = {"artifact": True, "no_error": False, "cost": True}
    assert evaluate_formula(formula, results) is False


def test_proof_is_human_readable():
    formula = Formula(Operator.AND, ["artifact", "no_error"])
    results = {"artifact": True, "no_error": False}
    proof = build_proof(formula, results)
    assert "artifact: PASS" in proof
    assert "no_error: FAIL" in proof
    assert "Verdict: FAIL" in proof
    assert "and" in proof.lower()


def test_proof_shows_pass_verdict_when_all_true():
    formula = Formula(Operator.AND, ["a", "b"])
    proof = build_proof(formula, {"a": True, "b": True})
    assert "Verdict: PASS" in proof