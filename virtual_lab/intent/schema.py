"""Versioned, bounded contracts for numerical predictions and reviewed outcomes."""

from datetime import datetime
import math
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class IntentError(ValueError):
    pass


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Feature(Strict):
    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
    unit: str = Field(min_length=1, max_length=100)
    offset: float = 0.0
    scale: float = Field(default=1.0, gt=0)

    @field_validator("offset", "scale")
    @classmethod
    def finite(cls, v):
        if not math.isfinite(v):
            raise ValueError("Finite encoding parameters required")
        return v


class TargetSchema(Strict):
    schema_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
    version: Literal[1] = 1
    description: str = Field(min_length=10, max_length=2000)
    features: list[Feature] = Field(min_length=1, max_length=32)
    outcome_name: str = Field(min_length=1, max_length=100)
    outcome_unit: str = Field(min_length=1, max_length=100)
    target_offset: float = 0.0
    target_scale: float = Field(default=1.0, gt=0)

    @model_validator(mode="after")
    def check(self):
        if len({f.name for f in self.features}) != len(self.features):
            raise ValueError("Duplicate feature names")
        if not math.isfinite(self.target_offset) or not math.isfinite(
            self.target_scale
        ):
            raise ValueError("Finite target encoding required")
        return self

    def encode(self, conditions):
        if not isinstance(conditions, dict) or set(conditions) != {
            f.name for f in self.features
        }:
            raise IntentError(
                "Conditions must match the versioned feature schema exactly"
            )
        values = []
        for f in self.features:
            raw = conditions[f.name]
            if type(raw) not in (int, float) or not math.isfinite(raw):
                raise IntentError("Finite numerical conditions required")
            value = (raw - f.offset) / f.scale
            if not math.isfinite(value) or abs(value) > 10:
                raise IntentError("Encoded conditions exceed [-10,10]")
            values.append(float(value))
        return values

    def encode_target(self, value, unit):
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or unit != self.outcome_unit
        ):
            raise IntentError(
                "Measured outcome value/units do not match the target schema"
            )
        normalized = (value - self.target_offset) / self.target_scale
        if not 0 <= normalized <= 1:
            raise IntentError(
                "Outcome is outside the defined target normalization [0,1]"
            )
        return float(normalized)


class LearningConfig(Strict):
    hidden: int = Field(default=16, ge=1, le=64)
    learning_rate: float = Field(default=0.06, gt=0, le=0.2)
    replay_capacity: int = Field(default=64, ge=0, le=256)
    replay_count: int = Field(default=2, ge=0, le=16)
    epochs_per_update: int = Field(default=1, ge=1, le=16)
    seed: int = Field(default=31, ge=0, le=2**32 - 1)

    @model_validator(mode="after")
    def valid(self):
        if (
            not math.isfinite(self.learning_rate)
            or self.replay_count > self.replay_capacity
        ):
            raise ValueError("Invalid learning/replay configuration")
        return self


class FeaturesPolicy(Strict):
    version: Literal[1] = 1
    predictions_enabled: bool = False
    learning_enabled: bool = False
    training_projects: list[str] = Field(default_factory=list, max_length=100)


class MeasuredOutcome(Strict):
    format: Literal["intent-measured-outcome-v1"] = "intent-measured-outcome-v1"
    experiment_id: str
    schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    group_id: str = Field(min_length=1, max_length=100)
    value: float
    unit: str = Field(min_length=1, max_length=100)
    acquired_at_utc: str

    @field_validator("value")
    @classmethod
    def finite(cls, v):
        if not math.isfinite(v):
            raise ValueError("Nonfinite outcome")
        return v

    @field_validator("acquired_at_utc")
    @classmethod
    def timestamp(cls, v):
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError("Timezone-aware acquisition time required")
        return dt.isoformat()


class Review(Strict):
    format: Literal["intent-training-review-v1"] = "intent-training-review-v1"
    model_id: str
    project_id: str
    experiment_id: str
    prediction_id: str
    observation_id: str
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    group_id: str = Field(min_length=1, max_length=100)
    purpose: Literal["train", "holdout"]
    permitted_data_use: Literal[True]
    reviewer_id: str = Field(min_length=1, max_length=100)
    expires_at_utc: str

    @field_validator("permitted_data_use", mode="before")
    @classmethod
    def explicit(cls, v):
        if v is not True:
            raise ValueError("Explicit signed data-use permission required")
        return v
