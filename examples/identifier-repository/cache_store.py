class LookupCache:
    def __init__(self):
        self._entries = {}

    def store_entry(self, key, value):
        self._entries[key] = value

    def cache_lookup(self, key):
        return self._entries.get(key)
