from solution import get_value

def test_get_value():
    assert get_value({"a": 1}, "a") == 1
    assert get_value({"a": 1}, "b") is None
