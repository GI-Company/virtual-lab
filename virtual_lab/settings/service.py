"""One cancellable process slot shared with INTENT; no implicit provider fallback."""
from __future__ import annotations
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
from .credentials import OSCredentials
from .repository import SettingsRepository, Settings

def route_for(provider):
    if provider.kind == 'mlx':
        return None
    if provider.kind in ('gemini', 'vertex'):
        return 'cloud'
    url = urlsplit(provider.endpoint)
    if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('Use an HTTP(S) server URL without credentials, query or fragment')
    host = url.hostname.lower()
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        # Only literal addresses / localhost qualify as local. DNS names require cloud permission.
        return 'loopback' if host == 'localhost' else 'cloud'
    if addr.is_loopback:
        return 'loopback'
    if addr.is_unspecified or addr.is_multicast or addr.is_link_local or addr.is_reserved:
        raise ValueError('Unsupported server address')
    return 'lan' if addr.is_private else 'cloud'

def credential_account(provider):
    if provider.kind != 'compatible':
        return provider.kind
    endpoint = provider.endpoint.rstrip('/')
    return 'compatible:' + hashlib.sha256(endpoint.encode()).hexdigest()

class SettingsService:
    def __init__(self, repository=None):
        self.repository = repository or SettingsRepository()
        self.credentials = OSCredentials()
        self._lock = threading.RLock()
        self._process = None
        self._reserved = None
        self._cancel = threading.Event()
        self.last_status = 'Idle; no model loaded'
        self.changed = None
        self.context = lambda: (None, None)

    @property
    def busy(self):
        with self._lock:
            return self._reserved is not None

    def reserve(self, owner):
        with self._lock:
            if self._reserved is not None:
                raise RuntimeError('Inference or training is active; cancel or wait first')
            self._reserved = owner
            self._cancel.clear()

    def release(self, owner):
        with self._lock:
            if self._reserved == owner:
                self._reserved = None

    def save(self, value):
        with self._lock:
            if self.busy:
                raise RuntimeError('Cancel the active inference or training job before changing settings')
            result = self.repository.save(value)
        if self.changed:
            self.changed()
        return result

    def resource_status(self):
        s = self.repository.load()
        root = Path(s.model_directory or self.repository.root / 'models').expanduser()
        existing = root
        while not existing.exists():
            existing = existing.parent
        free = shutil.disk_usage(existing).free
        return {'model_directory': str(root), 'free_gib': free / 1024**3,
                'minimum_free_gib': s.min_free_gib, 'process_loaded': self._process is not None,
                'busy': self.busy, 'status': self.last_status}

    def capabilities(self):
        provider = self.repository.load().provider
        return {'adapter': provider.kind, 'text': True, 'tools': False,
                'model_discovery': provider.kind == 'compatible',
                'embedded': provider.kind == 'mlx',
                'qualification': 'Adapter support only; selected model is unvalidated'}

    def registry(self):
        s = self.repository.load()
        entries = []
        root = Path(s.model_directory or self.repository.root / 'models').expanduser()
        if root.exists():
            for config in sorted(root.glob('*/config.json'))[:100]:
                entries.append({'name': config.parent.name, 'path': str(config.parent),
                                'capability': 'MLX text candidate; load not verified'})
        return entries

    def cancel(self):
        with self._lock:
            self._cancel.set()
            if self._process is not None and self._process.poll() is None:
                self._process.terminate()
        self.last_status = 'Cancellation requested; worker releases memory on exit'

    def unload(self):
        self.cancel()
        # Each request owns a separate process; there is no persistent SDK/model singleton.

    def request(self, prompt, *, discover=False, test=False):
        owner = object()
        self.reserve(owner)
        process = None
        try:
            project, experiment = self.context()
            s = self.repository.require('assistant', project, experiment)
            route = route_for(s.provider)
            self.repository.require('assistant', project, experiment, route=route)
            if not s.provider.model and not discover:
                raise ValueError('Select an explicit model identifier')
            if len(prompt) > 100000:
                raise ValueError('Prompt exceeds supported size')
            if s.provider.kind == 'mlx':
                status = self.resource_status()
                if status['free_gib'] < s.min_free_gib:
                    raise RuntimeError('Insufficient free disk space for local model operation')
                model = Path(s.provider.model_path).expanduser()
                if not s.provider.model_path or not model.is_dir() or not (model/'config.json').is_file():
                    raise ValueError('Select an existing local model directory containing config.json')
                total = sum(f.stat().st_size for f in model.rglob('*') if f.is_file())
                if total > s.max_model_gib * 1024**3:
                    raise RuntimeError('Model files exceed the configured model-size limit')
            key = self.credentials.get_api_key(credential_account(s.provider)) or ''
            if s.provider.kind in ('gemini', 'vertex') and not key and not (s.provider.kind == 'vertex' and s.provider.project):
                raise ValueError('Configure an OS-store credential or explicit Vertex project for ADC')
            request = {'provider': s.provider.model_dump(), 'prompt': prompt, 'key': key,
                       'max_tokens': s.max_tokens, 'timeout': s.timeout_seconds,
                       'discover': discover, 'test': test}
            # Deliberately exclude inherited SDK routing/credential environment settings.
            env = {k:v for k,v in os.environ.items() if not (k.startswith('VIRTUALLAB_') or k.startswith('GOOGLE_') or k in ('GEMINI_API_KEY','HTTPS_PROXY','HTTP_PROXY','ALL_PROXY','https_proxy','http_proxy','all_proxy'))}
            env['PYTHONUNBUFFERED'] = '1'
            process = subprocess.Popen([sys.executable, '-m', 'virtual_lab.settings.worker'],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                       env=env)
            with self._lock:
                self._process = process
                if self._cancel.is_set():
                    process.terminate()
            self.last_status = f'Running {s.provider.kind} ({route or "embedded"}); no fallback'
            payload = json.dumps(request).encode()
            started = time.monotonic()
            while True:
                if self._cancel.is_set():
                    raise RuntimeError('Request cancelled; no result accepted')
                # Recheck switches and scoped policy during execution, before any result is accepted.
                self.repository.require('assistant', project, experiment, route=route)
                if time.monotonic() - started > s.timeout_seconds:
                    raise TimeoutError('Provider timeout; no fallback attempted')
                try:
                    output, _ = process.communicate(payload, timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    payload = None
            if self._cancel.is_set():
                raise RuntimeError('Request cancelled; no result accepted')
            self.repository.require('assistant', project, experiment, route=route)
            if self.context() != (project, experiment):
                raise RuntimeError('Research context changed; provider result discarded')
            if process.returncode or len(output) > 2*1024*1024:
                raise RuntimeError('Provider failed or response exceeded limit; no fallback attempted')
            result = json.loads(output)
            if not result.get('ok'):
                raise RuntimeError('Provider request failed; check configuration and credentials (details withheld)')
            self.last_status = 'Completed; worker exited and model memory released'
            return result['result']
        except BaseException:
            self.last_status = 'Failed or cancelled; worker cleanup requested; no fallback attempted'
            raise
        finally:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
                for stream in (process.stdin, process.stdout):
                    if stream:
                        stream.close()
            with self._lock:
                self._process = None
            self.release(owner)
