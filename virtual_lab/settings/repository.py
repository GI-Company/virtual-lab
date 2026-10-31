"""Versioned private settings. Local OS access is the administration boundary."""
from __future__ import annotations
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from virtual_lab.core.paths import app_data_dir
from virtual_lab.pilots.storage import checked_path, read_bounded

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class Restrictions(Strict):
    mcp: bool = True
    assistant: bool = True
    predictions: bool = True
    learning: bool = True
    tools: bool = True
    exports: bool = True
    loopback: bool = True
    lan: bool = True
    cloud: bool = True

class MCPAccess(Strict):
    metadata: bool = False
    reports: bool = False
    spectrum: bool = False

class Provider(Strict):
    kind: Literal['gemini', 'vertex', 'mlx', 'compatible'] = 'compatible'
    model: str = Field(default='', max_length=200)
    endpoint: str = Field(default='http://127.0.0.1:1234/v1', max_length=500)
    model_path: str = Field(default='', max_length=2000)
    project: str = Field(default='', max_length=200)
    location: str = Field(default='global', max_length=100)

    @model_validator(mode='after')
    def endpoint_without_secrets(self):
        from urllib.parse import urlsplit
        url = urlsplit(self.endpoint)
        if url.username or url.password or url.query or url.fragment:
            raise ValueError('Provider URLs must not contain credentials, query or fragment')
        if self.kind == 'compatible' and (url.scheme not in ('http', 'https') or not url.hostname):
            raise ValueError('Use an explicit HTTP(S) server base URL')
        return self

class Settings(Strict):
    version: Literal[1] = 1
    mcp_enabled: bool = False
    mcp_projects: dict[str, MCPAccess] = Field(default_factory=dict)
    assistant_enabled: bool = False
    predictions_enabled: bool = False
    learning_enabled: bool = False
    allow_loopback: bool = True
    allow_lan: bool = False
    allow_cloud: bool = False
    allow_tools: bool = False
    allow_exports: bool = True
    provider: Provider = Field(default_factory=Provider)
    model_directory: str = Field(default='', max_length=2000)
    min_free_gib: int = Field(default=5, ge=1, le=10000)
    timeout_seconds: int = Field(default=90, ge=5, le=600)
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    max_model_gib: int = Field(default=8, ge=1, le=1024)
    project_rules: dict[str, Restrictions] = Field(default_factory=dict)
    experiment_rules: dict[str, Restrictions] = Field(default_factory=dict)

    @model_validator(mode='after')
    def paths(self):
        for value in (self.model_directory, self.provider.model_path):
            if value and not Path(value).expanduser().is_absolute():
                raise ValueError('Model locations must be absolute paths')
        return self

class SettingsRepository:
    def __init__(self, root=None, *, admin_path=None):
        self.root = checked_path(root or app_data_dir())
        self.path = self.root / 'settings.json'
        self.admin_path = admin_path or os.environ.get('VIRTUALLAB_ADMIN_POLICY')
        self.lock = threading.RLock()

    def load(self):
        with self.lock:
            if not self.path.exists():
                return Settings()
            raw = read_bounded(self.path, 1024*1024)
            from virtual_lab.core.provenance_export import reject_duplicates
            data = json.loads(raw, object_pairs_hook=reject_duplicates)
            # Explicit v0 migration; never ingest credentials or environment switches.
            if not isinstance(data, dict) or type(data.get('version', 1)) is not int:
                raise ValueError('Settings must be an object with an integer schema version')
            if data.get('version') == 0:
                data['version'] = 1
                data.setdefault('assistant_enabled', False)
            return Settings.model_validate(data)

    def save(self, settings):
        value = Settings.model_validate(settings)
        with self.lock:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            checked_path(self.path)
            fd, name = tempfile.mkstemp(prefix='.settings-', dir=self.root)
            try:
                with os.fdopen(fd, 'w') as stream:
                    json.dump(value.model_dump(), stream, indent=2, allow_nan=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, self.path)
            finally:
                if os.path.exists(name):
                    os.unlink(name)
        return value

    def administrator(self):
        if not self.admin_path:
            return Restrictions()
        return Restrictions.model_validate_json(read_bounded(self.admin_path, 65536))

    def require(self, operation, project_id=None, experiment_id=None, *, route=None):
        s = self.load()
        flags = dict(mcp=s.mcp_enabled, assistant=s.assistant_enabled, predictions=s.predictions_enabled,
                     learning=s.learning_enabled, tools=s.allow_tools, exports=s.allow_exports,
                     loopback=s.allow_loopback, lan=s.allow_lan, cloud=s.allow_cloud)
        for key in (operation, route):
            if key is None:
                continue
            if key not in flags or not flags[key]:
                raise PermissionError(f'{key} is disabled in Settings')
            for rule in (self.administrator(), s.project_rules.get(project_id), s.experiment_rules.get(experiment_id)):
                if rule is not None and not getattr(rule, key):
                    raise PermissionError(f'{key} is restricted by administrator, project or experiment policy')
        return s
