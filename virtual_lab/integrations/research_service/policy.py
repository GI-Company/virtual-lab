"""Operator-owned grants, loaded for each dispatch and again before release."""
import json
import time
from typing import Literal

from pydantic import Field, model_validator

from virtual_lab.core.provenance_export import reject_duplicates
from virtual_lab.pilots.storage import checked_path, read_bounded
from virtual_lab.settings.repository import Strict


class NotFound(Exception):
    """Same response for missing resources and resources outside the principal's grant."""


class Unavailable(Exception):
    pass


class Grant(Strict):
    subject: str = Field(min_length=1, max_length=200)
    tenant_id: str = Field(min_length=1, max_length=100)
    project_id: str = Field(min_length=1, max_length=100)
    research_access: bool = False
    metadata: bool = False
    reports: bool = False
    spectrum: bool = False
    changes: bool = False


class AccessPolicy(Strict):
    format: Literal['virtuallab-service-access-v1'] = 'virtuallab-service-access-v1'
    instance_id: str = Field(min_length=1, max_length=100)
    enabled: bool = False
    grants: list[Grant] = Field(default_factory=list, max_length=10000)
    revoked_token_ids: list[str] = Field(default_factory=list, max_length=10000)

    @model_validator(mode='after')
    def unique_memberships(self):
        pairs, tenants = set(), {}
        for g in self.grants:
            pair = (g.subject, g.project_id)
            if pair in pairs or tenants.get(g.project_id, g.tenant_id) != g.tenant_id:
                raise ValueError('Each project has one tenant and each membership is unique')
            pairs.add(pair)
            tenants[g.project_id] = g.tenant_id
        return self

    def authorize(self, principal, instance_id, project_id, category):
        if not self.enabled or self.instance_id != instance_id:
            raise NotFound()
        if principal.expires <= time.time() or principal.token_id in self.revoked_token_ids:
            raise NotFound()
        grant = next((g for g in self.grants if g.subject == principal.subject and g.project_id == project_id), None)
        if not grant or not grant.research_access or not getattr(grant, category):
            raise NotFound()
        return grant


class PolicyRepository:
    def __init__(self, path):
        self.path = checked_path(path)

    def load(self):
        try:
            return AccessPolicy.model_validate(json.loads(read_bounded(self.path, 1024*1024), object_pairs_hook=reject_duplicates))
        except (OSError, ValueError) as exc:
            raise Unavailable() from exc
