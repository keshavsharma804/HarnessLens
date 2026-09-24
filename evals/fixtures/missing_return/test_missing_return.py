from solution import max_of_three

def test_max_of_three():
    assert max_of_three(1, 2, 3) == 3
    assert max_of_three(5, 4, 3) == 5
    assert max_of_three(1, 5, 3) == 5
