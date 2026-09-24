def countdown(n):
    """Return list from n down to 1."""
    result = []
    while n > 0:
        result.append(n)
        # BUG: n is never decremented
    return result
