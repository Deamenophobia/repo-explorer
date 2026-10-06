"""Authored examples with similarly named methods and different expiry rules."""


class DeadlineCache:
    def __init__(self):
        self.values = {}
        self.deadlines = {}

    def store(self, key, value, deadline):
        self.values[key] = value
        self.deadlines[key] = deadline

    def expire(self, now):
        """Remove entries whose deadline has arrived."""
        removed = []
        for key, deadline in list(self.deadlines.items()):
            if deadline <= now:
                removed.append(self.values.pop(key))
                del self.deadlines[key]
        return removed


class ManualCache:
    def __init__(self):
        self.values = {}

    def store(self, key, value):
        self.values[key] = value

    def expire(self, key):
        """Remove the explicitly selected entry."""
        return self.values.pop(key, None)
