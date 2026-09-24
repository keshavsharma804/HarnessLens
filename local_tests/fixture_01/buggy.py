"""A tiny module with one deliberate bug."""


def add(a, b):
    """Return the sum of a and b."""
    return a - b   # <-- BUG: should be a + b


def multiply(a, b):
    """Return the product of a and b."""
    return a * b


def average(numbers):
    """Return the average of a list of numbers."""
    if not numbers:
        raise ValueError("Cannot average an empty list")
    return sum(numbers) / len(numbers)