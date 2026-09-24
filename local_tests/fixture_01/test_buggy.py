"""Tests for buggy.py. Currently failing on test_add."""
from buggy import add, multiply, average


def test_add():
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
    assert add(0, 0) == 0


def test_multiply():
    assert multiply(2, 3) == 6
    assert multiply(-1, 5) == -5


def test_average():
    assert average([1, 2, 3]) == 2
    assert average([10]) == 10