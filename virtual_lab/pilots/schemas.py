"""Strict interchange contract for the local MS workflow (no scientific inference)."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import datetime, timezone

MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_PEAKS = 100_000
MAX_MANIFEST_BYTES = 64 * 1024
PROCESSING_VERSION = 'centroid-decimal-sort-v2'
Identifier = Annotated[str, Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$', max_length=80)]
Digest = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$', max_length=64)]

class PilotError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def utc_timestamp(value):
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc).isoformat()
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError('Acquisition timestamp requires ISO 8601 with timezone') from exc


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class AcquisitionMetadata(StrictModel):
    pilot_id: Identifier = 'mild-biotec-initial-ms'
    dataset_id: Identifier
    sample_id: Identifier
    instrument_id: Identifier
    operator_id: Identifier
    acquired_at_utc: str | None = None
    mz_units: str | None = Field(default=None, max_length=100)
    intensity_units: str | None = Field(default=None, max_length=100)

    @field_validator('acquired_at_utc')
    @classmethod
    def timestamp(cls, value):
        return utc_timestamp(value)

    @field_validator('mz_units', 'intensity_units')
    @classmethod
    def units(cls, value):
        if value is not None and (not value.strip() or any(ord(c) < 32 for c in value)):
            raise ValueError('Provide units or leave them unspecified')
        return value


class Artifact(StrictModel):
    file: Literal['source.csv', 'peaks.csv']
    sha256: Digest
    size_bytes: int = Field(gt=0, le=MAX_SOURCE_BYTES * 4)


class Manifest(AcquisitionMetadata):
    schema_version: Literal[2]
    run_id: Identifier
    created_at_utc: str
    source_filename: str = Field(max_length=255)
    data_kind: Literal['centroid_peak_list']
    epistemic_state: Literal['UNKNOWN']
    import_status: Literal['accepted']
    input_format: Literal['strict_csv_mz_intensity_v1']
    processing_version: Literal['centroid-decimal-sort-v2']
    software_version: str = Field(max_length=100)
    peak_count: int = Field(gt=0, le=MAX_PEAKS)
    source_sha256: Digest
    normalized_sha256: Digest
    approved_nonconfidential: Literal[True]
    duplicate_of: list[Identifier] = Field(max_length=1000)
    warnings: list[str] = Field(max_length=20)
    limitations: list[str] = Field(min_length=1, max_length=20)
    artifacts: list[Artifact] = Field(min_length=2, max_length=2)

    @field_validator('created_at_utc')
    @classmethod
    def created(cls, value):
        return utc_timestamp(value)

    @field_validator('artifacts')
    @classmethod
    def inventory(cls, value):
        if {v.file for v in value} != {'source.csv', 'peaks.csv'}:
            raise ValueError('Manifest must contain exactly source.csv and peaks.csv')
        return value
