def get_value(d, key):
    """Return the value for key, or None if missing."""
    return d[key]  # BUG: raises KeyError instead of returning None
