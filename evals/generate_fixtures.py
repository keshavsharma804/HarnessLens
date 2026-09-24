"""Generate 10 bug-fix fixtures programmatically."""

from pathlib import Path

FIXTURES = [
    # (name, buggy_code, test_code, instructions)
    (
        "off_by_one",
        '''def sum_range(n):
    """Return sum of 0..n inclusive."""
    total = 0
    for i in range(n):  # BUG: should be range(n + 1)
        total += i
    return total
''',
        '''from solution import sum_range

def test_sum_range():
    assert sum_range(0) == 0
    assert sum_range(3) == 6
    assert sum_range(5) == 15
''',
        "Fix the off-by-one error in sum_range so tests pass.",
    ),
    (
        "wrong_operator",
        '''def divide(a, b):
    """Return a divided by b."""
    return a * b  # BUG: should be a / b
''',
        '''from solution import divide

def test_divide():
    assert divide(10, 2) == 5
    assert divide(9, 3) == 3
''',
        "Fix the operator in divide so tests pass.",
    ),
    (
        "missing_return",
        '''def max_of_three(a, b, c):
    """Return the maximum of three numbers."""
    if a >= b and a >= c:
        return a
    if b >= a and b >= c:
        return b
    # BUG: missing return statement
''',
        '''from solution import max_of_three

def test_max_of_three():
    assert max_of_three(1, 2, 3) == 3
    assert max_of_three(5, 4, 3) == 5
    assert max_of_three(1, 5, 3) == 5
''',
        "Fix max_of_three so it always returns a value.",
    ),
    (
        "wrong_condition",
        '''def is_even(n):
    """Return True if n is even."""
    return n % 2 == 1  # BUG: should be == 0
''',
        '''from solution import is_even

def test_is_even():
    assert is_even(2) is True
    assert is_even(4) is True
    assert is_even(3) is False
''',
        "Fix is_even so tests pass.",
    ),
    (
        "swap_values",
        '''def swap(a, b):
    """Return a tuple (b, a)."""
    return (a, b)  # BUG: should be (b, a)
''',
        '''from solution import swap

def test_swap():
    assert swap(1, 2) == (2, 1)
    assert swap("a", "b") == ("b", "a")
''',
        "Fix swap so it returns the values in reverse order.",
    ),
    (
        "string_concat",
        '''def greet(name):
    """Return 'Hello, <name>!'."""
    return "Hello, " + name  # BUG: missing '!'
''',
        '''from solution import greet

def test_greet():
    assert greet("World") == "Hello, World!"
    assert greet("Alice") == "Hello, Alice!"
''',
        "Fix greet so it includes the exclamation mark.",
    ),
    (
        "list_append",
        '''def add_item(items, item):
    """Add item to the list and return it."""
    return items + [item]  # works but returns new list; test expects mutation
''',
        '''from solution import add_item

def test_add_item():
    items = [1, 2]
    result = add_item(items, 3)
    assert result == [1, 2, 3]
    assert items == [1, 2, 3]  # expects mutation
''',
        "Fix add_item so the original list is mutated.",
    ),
    (
        "dict_key_error",
        '''def get_value(d, key):
    """Return the value for key, or None if missing."""
    return d[key]  # BUG: raises KeyError instead of returning None
''',
        '''from solution import get_value

def test_get_value():
    assert get_value({"a": 1}, "a") == 1
    assert get_value({"a": 1}, "b") is None
''',
        "Fix get_value so it returns None for missing keys.",
    ),
    (
        "loop_infinite",
        '''def countdown(n):
    """Return list from n down to 1."""
    result = []
    while n > 0:
        result.append(n)
        # BUG: n is never decremented
    return result
''',
        '''from solution import countdown

def test_countdown():
    assert countdown(3) == [3, 2, 1]
    assert countdown(1) == [1]
''',
        "Fix countdown so it terminates and returns the correct list.",
    ),
    (
        "wrong_slice",
        '''def first_three(items):
    """Return the first three elements."""
    return items[:2]  # BUG: should be items[:3]
''',
        '''from solution import first_three

def test_first_three():
    assert first_three([1, 2, 3, 4, 5]) == [1, 2, 3]
    assert first_three([1, 2]) == [1, 2]
''',
        "Fix first_three so it returns up to three elements.",
    ),
]


def main():
    root = Path("evals/fixtures")
    root.mkdir(parents=True, exist_ok=True)

    for name, buggy, test, instructions in FIXTURES:
        folder = root / name
        folder.mkdir(exist_ok=True)
        (folder / "solution.py").write_text(buggy)
        (folder / f"test_{name}.py").write_text(test)
        (folder / "INSTRUCTIONS.md").write_text(
            f"# Task\n\n{instructions}\n\n"
            "Do NOT modify the test file.\n"
            "Do NOT install anything.\n"
        )
        print(f"  Created: {name}")

    print(f"\nTotal fixtures: {len(FIXTURES)}")
    print(f"Location: {root.resolve()}")


if __name__ == "__main__":
    main()