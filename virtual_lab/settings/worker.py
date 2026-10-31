"""Ephemeral SDK/model worker. Secrets arrive on stdin and never enter logs."""
import json
import sys

def compatible(r):
    import urllib.request
    import urllib.error
    from urllib.parse import urlsplit
    from virtual_lab.settings.repository import Provider
    from virtual_lab.settings.service import route_for
    p = Provider.model_validate(r['provider'])
    route_for(p)
    # No redirects or proxy substitution: an endpoint cannot silently route elsewhere.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    headers = {'Content-Type':'application/json'}
    if r['key']:
        headers['Authorization'] = 'Bearer ' + r['key']
    if r['discover']:
        path, payload = '/models', None
    else:
        path = '/chat/completions'
        payload = json.dumps({'model':p.model, 'messages':[{'role':'user','content':r['prompt']}],
                              'max_tokens':r['max_tokens'], 'stream':False}).encode()
    endpoint = p.endpoint
    parsed = urlsplit(endpoint)
    if parsed.hostname == 'localhost':
        endpoint = parsed._replace(netloc='127.0.0.1' + (':' + str(parsed.port) if parsed.port else '')).geturl()
    req = urllib.request.Request(endpoint.rstrip('/')+path, data=payload, headers=headers)
    with opener.open(req, timeout=r['timeout']) as response:
        raw = response.read(2*1024*1024+1)
    if len(raw) > 2*1024*1024:
        raise ValueError('Response limit')
    data = json.loads(raw)
    if r['discover']:
        return [str(m['id'])[:200] for m in data['data'][:100]]
    text = data['choices'][0]['message']['content']
    if not isinstance(text, str):
        raise ValueError('Text response required')
    return text

def run(r):
    p = r['provider']
    if p['kind'] == 'compatible':
        return compatible(r)
    if r['discover']:
        raise ValueError('Discovery is supported by compatible servers only; configure an explicit model otherwise')
    if p['kind'] == 'mlx':
        import os
        os.environ['VIRTUALLAB_LOCAL_MODEL'] = p['model_path']
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        from virtual_lab.ai.providers.mlx_local import MLXLocalProvider
        return MLXLocalProvider().chat([{'role':'user','content':r['prompt']}], max_tokens=r['max_tokens'], enable_thinking=False).text
    from google import genai
    if p['kind'] == 'gemini':
        client = genai.Client(vertexai=False, api_key=r['key'])
    elif p['kind'] == 'vertex':
        client = genai.Client(vertexai=True, api_key=r['key']) if r['key'] else genai.Client(vertexai=True, project=p['project'], location=p['location'])
    else:
        raise ValueError('Unsupported provider')
    try:
        result = client.models.generate_content(model=p['model'], contents=r['prompt'],
                    config={'max_output_tokens':r['max_tokens']})
        return result.text or ''
    finally:
        client.close()

def main():
    try:
        r = json.loads(sys.stdin.buffer.read(1024*1024))
        result = run(r)
        sys.stdout.write(json.dumps({'ok':True, 'result':result}))
    except Exception:
        sys.stdout.write('{"ok":false}')

if __name__ == '__main__':
    main()
