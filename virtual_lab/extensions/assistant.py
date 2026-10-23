"""Explicit OpenAI-compatible text endpoint; no tools, execution or credentials on disk."""
import ipaddress
import json
import urllib.request
from urllib.parse import urlsplit
from virtual_lab.core.canonical import canonical_json, strict_json_loads


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Assistant redirects are not permitted.')


class AssistantEndpoint:
    def __init__(self, endpoint, model, api_key=None):
        parsed = urlsplit(endpoint)
        local = parsed.hostname == 'localhost'
        try: local = local or ipaddress.ip_address(parsed.hostname).is_loopback
        except (ValueError, TypeError): pass
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or (parsed.scheme == 'http' and not local)):
            raise ValueError('Use explicit HTTPS or loopback HTTP, without URL credentials, query or fragment.')
        if not isinstance(model, str) or not model.strip() or len(model) > 200:
            raise ValueError('Supply the provider model identifier.')
        self.endpoint, self.model, self.api_key = endpoint, model, api_key

    def critique(self, prompt, *, allow_network=False):
        if not allow_network: raise ValueError('Explicit network opt-in required.')
        if not isinstance(prompt, str) or not 1 <= len(prompt) <= 32000: raise ValueError('Prompt size limit.')
        headers = {'Content-Type': 'application/json'}
        if self.api_key: headers['Authorization'] = 'Bearer ' + self.api_key
        request = urllib.request.Request(self.endpoint, data=canonical_json({
            'model': self.model, 'messages': [{'role': 'user', 'content': prompt}], 'stream': False,
            'max_tokens': 1024}), headers=headers)
        # Disable redirects and implicit proxies so authorization cannot migrate.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        try:
            with opener.open(request, timeout=30) as response: raw = response.read(1024*1024+1)
        except Exception:
            raise ValueError('Assistant request failed; verify endpoint configuration and connectivity.') from None
        if len(raw) > 1024*1024: raise ValueError('Assistant response size limit.')
        data = strict_json_loads(raw)
        try: text = data['choices'][0]['message']['content']
        except (KeyError, IndexError, TypeError): raise ValueError('Unsupported assistant response.') from None
        if not isinstance(text, str) or len(text) > 64000: raise ValueError('Unsupported assistant text.')
        return {'kind': 'assistant', 'epistemic_state': 'INFERRED', 'authoritative': False,
                'provider_endpoint': self.endpoint, 'model_id': self.model, 'text': text,
                'prompt': prompt,
                'limitations': ['Advisory text; no tool authority or instrument control.',
                                'Provider identifier is not an immutable weights fingerprint.']}
