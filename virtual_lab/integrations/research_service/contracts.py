"""Versioned, path-free report projection for all authenticated reader clients."""
from typing import Literal
from pydantic import Field
from virtual_lab.application.contracts import ExperimentRef, Strict


class BasePeak(Strict):
    mz: str
    intensity: str


class Summary(Strict):
    peak_count: int = Field(ge=1)
    mz_min: str
    mz_max: str
    base_peak: BasePeak
    total_intensity: str
    duplicate_mz_count: int = Field(ge=0)
    note: str


class AcceptanceCheck(Strict):
    id: str
    label: str
    status: Literal['PASS','FAIL','NOT RUN']
    detail: str


class SharedMSReport(Strict):
    format: Literal['virtuallab-service-ms-report-v1'] = 'virtuallab-service-ms-report-v1'
    reference: ExperimentRef
    observation_id: str
    run_id: str
    data_origin: Literal['synthetic','public_reference','laboratory_supplied','unspecified']
    epistemic_state: Literal['UNKNOWN'] = 'UNKNOWN'
    source_sha256: str = Field(pattern='^[0-9a-f]{64}$')
    normalized_sha256: str = Field(pattern='^[0-9a-f]{64}$')
    manifest_sha256: str = Field(pattern='^[0-9a-f]{64}$')
    processing_version: str
    software_version: str
    summary: Summary
    acceptance_checks: list[AcceptanceCheck] = Field(min_length=5,max_length=5)
    workflow_check_status: Literal['PASS','FAIL','INCOMPLETE']
    review_status: Literal['approved','rejected','not_reviewed']
    verification_scope: str
