def sum_range(n):
    """Return sum of 0..n inclusive."""
    total = 0
    for i in range(n):  # BUG: should be range(n + 1)
        total += i
    return total
