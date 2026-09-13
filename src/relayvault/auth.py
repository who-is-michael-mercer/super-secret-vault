"""Local retry courtesy policy. It cannot constrain offline password guessing."""

import hashlib
import json
import os
import time
from . import settings
from .vault import store


class BackoffError(ValueError):
    pass


class RetryPolicy:
    def __init__(self, identity):
        directory = settings.private_directory(settings.home() / "authentication")
        self.path = directory / (
            hashlib.sha256(identity.encode()).hexdigest() + ".json"
        )

    def read(self):
        if not self.path.exists() and not self.path.is_symlink():
            return {"failures": 0, "until": 0}
        with store.open_regular(self.path) as source:
            if os.fstat(source.fileno()).st_size > 1024:
                raise ValueError("Invalid local retry state.")
            data = json.loads(source.read())
        if (
            not isinstance(data, dict)
            or set(data) != {"failures", "until"}
            or type(data["failures"]) is not int
            or not 0 <= data["failures"] < 3
            or type(data["until"]) not in (int, float)
            or not 0 <= data["until"] < 1e20
        ):
            raise ValueError("Invalid local retry state.")
        return data

    def write(self, data):
        with store.temporary(self.path.parent) as (stream, path):
            stream.write(json.dumps(data).encode())
            stream.flush()
            os.fsync(stream.fileno())
            store.publish(path, self.path, replace=True)

    def check(self):
        seconds = self.read()["until"] - time.time()
        if seconds > 0:
            raise BackoffError(f"Authentication backoff: {int(seconds)+1}s remaining.")

    def failure(self):
        data = self.read()
        failures = data["failures"] + 1
        self.write(
            {
                "failures": 0 if failures >= 3 else failures,
                "until": time.time() + 30 if failures >= 3 else 0,
            }
        )

    def success(self):
        self.write({"failures": 0, "until": 0})
