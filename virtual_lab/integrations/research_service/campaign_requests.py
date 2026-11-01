"""Strict, bounded inputs for the opt-in private campaign API."""
import asyncio
from dataclasses import MISSING, fields
import json
import re
from typing import get_type_hints
import uuid

from pydantic import ConfigDict, Field, create_model, field_validator
from starlette.requests import ClientDisconnect

from virtual_lab.application.simulation_runner import RunConfig
from virtual_lab.core.provenance_export import reject_duplicates
from virtual_lab.settings.repository import Strict

MAX_BODY_BYTES = 65536
BODY_TIMEOUT_SECONDS = 5

# Derive strict JSON validation from the engine's configuration rather than
# maintaining another scientific configuration with potentially different defaults.
_hints = get_type_hints(RunConfig)
_fields = {}
for _field in fields(RunConfig):
    _default = (Field(default_factory=_field.default_factory)
                if _field.default_factory is not MISSING else _field.default)
    _fields[_field.name] = (_hints[_field.name], _default)
SimulationInput = create_model('SimulationInput',
    __config__=ConfigDict(extra='forbid', strict=True), **_fields)


class CampaignCommand(Strict):
    request_id: str = Field(min_length=36, max_length=36)

    @field_validator('request_id')
    @classmethod
    def canonical_uuid(cls, value):
        if str(uuid.UUID(value)) != value:
            raise ValueError('Use a canonical UUID request ID')
        return value


class CreateCampaign(CampaignCommand):
    objective: str = Field(min_length=1, max_length=2000)
    configs: list[SimulationInput] = Field(min_length=1, max_length=20)
    max_runs: int = Field(ge=1, le=20)
    max_seconds: int = Field(ge=1, le=86400)


class StartCampaign(CampaignCommand):
    approved_plan_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class InvalidBody(Exception):
    def __init__(self, status=400):
        self.status = status


async def campaign_body(request, operation):
    """Reject declared/streamed oversize bodies without calling Request.body()."""
    headers = request.scope['headers']
    types = [value for key, value in headers if key == b'content-type']
    lengths = [value for key, value in headers if key == b'content-length']
    if (len(types) != 1 or types[0].lower() not in
            (b'application/json', b'application/json; charset=utf-8') or
            any(key == b'content-encoding' for key, _ in headers) or len(lengths) > 1):
        raise InvalidBody()
    declared = None
    if lengths:
        if not re.fullmatch(rb'[0-9]{1,10}', lengths[0]):
            raise InvalidBody()
        declared = int(lengths[0])
        if declared > MAX_BODY_BYTES:
            raise InvalidBody(413)

    async def collect():
        collected = bytearray()
        async for chunk in request.stream():
            if len(collected) + len(chunk) > MAX_BODY_BYTES:
                raise InvalidBody(413)
            collected.extend(chunk)
        if declared is not None and len(collected) != declared:
            raise InvalidBody()
        return bytes(collected)

    try:
        raw = await asyncio.wait_for(collect(), BODY_TIMEOUT_SECONDS)
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=reject_duplicates,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        model = {'campaign.create': CreateCampaign, 'campaign.start': StartCampaign,
                 'campaign.pause': CampaignCommand,
                 'campaign.cancel': CampaignCommand}[operation]
        body = model.model_validate(value).model_dump()
        if operation == 'campaign.create':
            for config in body['configs']:
                RunConfig(**config).validate()
        return body
    except asyncio.TimeoutError as exc:
        raise InvalidBody(408) from exc
    except (ValueError, TypeError, AttributeError, UnicodeError, RecursionError, ClientDisconnect) as exc:
        raise InvalidBody() from exc
