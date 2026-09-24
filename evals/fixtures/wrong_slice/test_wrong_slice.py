from solution import first_three

def test_first_three():
    assert first_three([1, 2, 3, 4, 5]) == [1, 2, 3]
    assert first_three([1, 2]) == [1, 2]
