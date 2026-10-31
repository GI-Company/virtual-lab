"""Versioned internal requests. Authentication belongs to the future transport."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class ExperimentRef(Strict):
    instance_id: str = Field(min_length=1, max_length=100)
    project_id: str = Field(min_length=1, max_length=100)
    experiment_id: str = Field(min_length=1, max_length=100)


class ChangeCursor(Strict):
    instance_id: str
    project_id: str
    sequence: int = Field(default=0, ge=0)


class JobStatus(Strict):
    format: Literal['virtuallab-job-v1'] = 'virtuallab-job-v1'
    id: str
    project_id: str
    experiment_id: str
    state: Literal['RUNNING','CANCELLING','COMPLETED','CANCELLED','FAILED','INTERRUPTED']
    result_observation_id: str | None = None
    error_code: str | None = None
