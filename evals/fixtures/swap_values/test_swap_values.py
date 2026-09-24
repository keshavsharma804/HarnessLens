from solution import swap

def test_swap():
    assert swap(1, 2) == (2, 1)
    assert swap("a", "b") == ("b", "a")
