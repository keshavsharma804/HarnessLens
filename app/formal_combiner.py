"""
Formal logic combiner for predicate results.

Takes a list of predicate results and a logical formula (in DNF or
operator form) and computes the final verdict deterministically.

This is the "symbolic" half of neuro-symbolic: the neural half answers
atomic questions, this half composes them with mathematical guarantees.

Supported operators: AND, OR, NOT, IMPLIES.
"""

from dataclasses import dataclass
from enum import Enum

from app.predicate_decomposer import PredicateResult


class Operator(str, Enum):
    AND = "and"
    OR = "or"
    NOT = "not"
    IMPLIES = "implies"


@dataclass
class Formula:
    operator: Operator
    operands: list  # str (predicate name) or Formula


def evaluate_formula(formula: Formula, results: dict[str, bool]) -> bool:
    """Evaluate a logical formula against predicate results."""
    if formula.operator == Operator.AND:
        return all(
            evaluate_formula(f, results) if isinstance(f, Formula)
            else results.get(f, False)
            for f in formula.operands
        )
    if formula.operator == Operator.OR:
        return any(
            evaluate_formula(f, results) if isinstance(f, Formula)
            else results.get(f, False)
            for f in formula.operands
        )
    if formula.operator == Operator.NOT:
        operand = formula.operands[0]
        value = (
            evaluate_formula(operand, results) if isinstance(operand, Formula)
            else results.get(operand, False)
        )
        return not value
    if formula.operator == Operator.IMPLIES:
        antecedent, consequent = formula.operands
        a = evaluate_formula(antecedent, results) if isinstance(antecedent, Formula) else results.get(antecedent, False)
        c = evaluate_formula(consequent, results) if isinstance(consequent, Formula) else results.get(consequent, False)
        return (not a) or c
    return False


def build_proof(formula: Formula, results: dict[str, bool]) -> str:
    """Produce a human-readable proof string from the formula and results."""
    lines = []
    for name, passed in results.items():
        lines.append(f"  {name}: {'PASS' if passed else 'FAIL'}")
    final = evaluate_formula(formula, results)
    lines.append(f"  Verdict: {'PASS' if final else 'FAIL'}")
    lines.append(f"  Formula: {formula.operator.value}({', '.join(str(o) for o in formula.operands)})")
    return "\n".join(lines)