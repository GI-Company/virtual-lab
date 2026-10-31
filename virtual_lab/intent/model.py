"""Bounded from-scratch regressor. Provenance/authorization belongs to Controller."""

import hashlib
import json
import math
import random
from virtual_lab.intent.schema import LearningConfig, IntentError


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


class MiniModel:
    architecture = "intent-experiment-mini-v2"

    def __init__(self, features, config=None):
        if type(features) is not int or not 1 <= features <= 32:
            raise IntentError("Unsupported feature count")
        self.features = features
        self.config = config or LearningConfig()
        self.rng = random.Random(self.config.seed)
        self.w1 = [
            [self.rng.uniform(-0.12, 0.12) for _ in range(features)]
            for _ in range(self.config.hidden)
        ]
        self.b1 = [0.0] * self.config.hidden
        self.w2 = [self.rng.uniform(-0.12, 0.12) for _ in range(self.config.hidden)]
        self.b2 = 0.0
        self.replay = []
        self.steps = 0

    def _features(self, x):
        if (
            not isinstance(x, list)
            or len(x) != self.features
            or any(
                type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 10
                for v in x
            )
        ):
            raise IntentError("Invalid bounded feature vector")
        return [float(v) for v in x]

    def _forward(self, x):
        h = [
            math.tanh(math.fsum(wj * xj for wj, xj in zip(w, x)) + b)
            for w, b in zip(self.w1, self.b1)
        ]
        z = math.fsum(w * v for w, v in zip(self.w2, h)) + self.b2
        y = 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))
        return y, h

    def predict(self, x):
        return self._forward(self._features(x))[0]

    def _step(self, x, target):
        y, h = self._forward(x)
        d = (y - target) * y * (1 - y)
        old = self.w2[:]
        lr = self.config.learning_rate
        for i in range(self.config.hidden):
            self.w2[i] -= lr * d * h[i]
            dh = d * old[i] * (1 - h[i] * h[i])
            for j in range(self.features):
                self.w1[i][j] -= lr * dh * x[j]
            self.b1[i] -= lr * dh
        self.b2 -= lr * d

    def fit_one(self, x, target, example_id):
        x = self._features(x)
        if (
            type(target) not in (int, float)
            or not math.isfinite(target)
            or not 0 <= target <= 1
        ):
            raise IntentError("Invalid normalized outcome")
        if not isinstance(example_id, str) or not 1 <= len(example_id) <= 200:
            raise IntentError("Invalid example ID")
        before = self.predict(x)
        for _ in range(self.config.epochs_per_update):
            self._step(x, target)
            for old in self.rng.sample(
                self.replay, min(len(self.replay), self.config.replay_count)
            ):
                self._step(old["x"], old["y"])
        if self.config.replay_capacity:
            self.replay = (
                self.replay + [{"x": x, "y": float(target), "id": example_id}]
            )[-self.config.replay_capacity :]
        self.steps += 1
        # Fail before publishing unstable model state.
        self.from_state(self.state())
        return {"preupdate_prediction": before, "absolute_error": abs(before - target)}

    def state(self):
        return {
            "architecture": self.architecture,
            "features": self.features,
            "config": self.config.model_dump(),
            "w1": self.w1,
            "b1": self.b1,
            "w2": self.w2,
            "b2": self.b2,
            "replay": self.replay,
            "steps": self.steps,
            "rng_state": self.rng.getstate(),
            "optimizer": "sgd-v1",
        }

    def digest(self):
        return hashlib.sha256(canonical(self.state())).hexdigest()

    @classmethod
    def from_state(cls, d):
        required = {
            "architecture",
            "features",
            "config",
            "w1",
            "b1",
            "w2",
            "b2",
            "replay",
            "steps",
            "rng_state",
            "optimizer",
        }
        if (
            not isinstance(d, dict)
            or set(d) != required
            or d["architecture"] != cls.architecture
            or d["optimizer"] != "sgd-v1"
        ):
            raise IntentError("Unsupported checkpoint schema")
        obj = cls(d["features"], LearningConfig.model_validate(d["config"]))
        hidden = obj.config.hidden

        def vector(v, n):
            return (
                isinstance(v, list)
                and len(v) == n
                and all(
                    type(x) in (int, float) and math.isfinite(x) and abs(x) <= 1e6
                    for x in v
                )
            )

        if (
            not isinstance(d["w1"], list)
            or len(d["w1"]) != hidden
            or not all(vector(v, obj.features) for v in d["w1"])
            or not vector(d["b1"], hidden)
            or not vector(d["w2"], hidden)
            or not vector([d["b2"]], 1)
        ):
            raise IntentError("Invalid checkpoint weights")
        if type(d["steps"]) is not int or not 0 <= d["steps"] <= 1000000:
            raise IntentError("Invalid checkpoint step count")
        if (
            not isinstance(d["replay"], list)
            or len(d["replay"]) > obj.config.replay_capacity
        ):
            raise IntentError("Replay limit exceeded")
        for old in d["replay"]:
            if not isinstance(old, dict) or set(old) != {"x", "y", "id"}:
                raise IntentError("Invalid replay example")
            obj._features(old["x"])
            if (
                type(old["y"]) not in (int, float)
                or not math.isfinite(old["y"])
                or not 0 <= old["y"] <= 1
                or not isinstance(old["id"], str)
                or len(old["id"]) > 200
            ):
                raise IntentError("Invalid replay example")
        state = d["rng_state"]
        if (
            not isinstance(state, (tuple, list))
            or len(state) != 3
            or state[0] != 3
            or len(state[1]) != 625
            or any(type(v) is not int or not 0 <= v <= 2**32 - 1 for v in state[1])
            or state[2] is not None
        ):
            raise IntentError("Invalid random state")
        for k in ("w1", "b1", "w2", "b2", "replay", "steps"):
            setattr(obj, k, d[k])
        obj.rng.setstate((3, tuple(state[1]), None))
        return obj
