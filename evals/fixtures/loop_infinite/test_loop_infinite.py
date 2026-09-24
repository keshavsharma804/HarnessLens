from solution import countdown

def test_countdown():
    assert countdown(3) == [3, 2, 1]
    assert countdown(1) == [1]
