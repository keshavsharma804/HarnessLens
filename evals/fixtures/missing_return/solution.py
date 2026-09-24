def max_of_three(a, b, c):
    """Return the maximum of three numbers."""
    if a >= b and a >= c:
        return a
    if b >= a and b >= c:
        return b
    # BUG: missing return statement
