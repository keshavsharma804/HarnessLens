from solution import add_item

def test_add_item():
    items = [1, 2]
    result = add_item(items, 3)
    assert result == [1, 2, 3]
    assert items == [1, 2, 3]  # expects mutation
