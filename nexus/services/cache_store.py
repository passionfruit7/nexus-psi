import time


class CacheStore:

    def __init__(self):
        self._values = {}

    def put(self, key, value):
        now = time.time()

        self._values[key] = {
            "value": value,
            "created_at": now,
        }

        return {
            "key": key,
            "value": value,
            "created_at": now,
        }

    def get(self, key):
        return self._values.get(key)

    def delete(self, key):
        self._values.pop(key, None)

    def clear(self):
        self._values.clear()
