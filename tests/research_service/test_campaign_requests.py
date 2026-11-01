import asyncio
import json
import uuid

import pytest
from starlette.requests import Request

from virtual_lab.integrations.research_service import campaign_requests as requests


def valid():
    return {'request_id': str(uuid.uuid4()), 'objective': 'Custom assumed concentration comparison',
            'configs': [{'model_id': 'gene_expression', 'members': 2, 'duration_h': 1}],
            'max_runs': 1, 'max_seconds': 60}


def make_request(receive, headers=()):
    return Request({'type': 'http', 'method': 'POST', 'path': '/campaigns',
                    'headers': [(b'content-type', b'application/json'), *headers]}, receive)


def test_declared_oversize_is_rejected_without_reading():
    async def receive():
        pytest.fail('Declared oversized input must not be read')
    request = make_request(receive, [(b'content-length', b'65537')])
    with pytest.raises(requests.InvalidBody) as exc:
        asyncio.run(requests.campaign_body(request, 'campaign.create'))
    assert exc.value.status == 413


def test_streaming_limit_stops_before_remaining_chunks():
    calls = []
    async def receive():
        calls.append(1)
        assert len(calls) <= 2
        return {'type': 'http.request', 'body': b'x' * 32769, 'more_body': True}
    with pytest.raises(requests.InvalidBody) as exc:
        asyncio.run(requests.campaign_body(make_request(receive), 'campaign.create'))
    assert exc.value.status == 413 and len(calls) == 2


def test_body_deadline(monkeypatch):
    monkeypatch.setattr(requests, 'BODY_TIMEOUT_SECONDS', .01)
    async def receive():
        await asyncio.sleep(10)
    with pytest.raises(requests.InvalidBody) as exc:
        asyncio.run(requests.campaign_body(make_request(receive), 'campaign.create'))
    assert exc.value.status == 408


@pytest.mark.parametrize('change', [
    lambda x: x.update(max_runs=True),
    lambda x: x['configs'][0].update(members='2'),
    lambda x: x['configs'][0].update(concentration_um=True),
    lambda x: x['configs'][0].update(arbitrary_path='/private'),
    lambda x: x.update(surface='admin'),
    lambda x: x.update(request_id='not-a-uuid'),
])
def test_strict_types_and_unknown_fields(change):
    value = valid()
    change(value)
    async def receive():
        return {'type': 'http.request', 'body': json.dumps(value).encode()}
    with pytest.raises(requests.InvalidBody):
        asyncio.run(requests.campaign_body(make_request(receive), 'campaign.create'))


@pytest.mark.parametrize('raw', [b'{"a":1,"a":2}', b'{"value":NaN}', b'\xff', b'[]'])
def test_malformed_json(raw):
    async def receive():
        return {'type': 'http.request', 'body': raw}
    with pytest.raises(requests.InvalidBody):
        asyncio.run(requests.campaign_body(make_request(receive), 'campaign.create'))


def test_valid_input_uses_engine_defaults_and_custom_parameters():
    value = valid()
    value['configs'][0]['concentration_um'] = 7.25
    async def receive():
        return {'type': 'http.request', 'body': json.dumps(value).encode()}
    body = asyncio.run(requests.campaign_body(make_request(receive), 'campaign.create'))
    assert body['configs'][0]['backend'] == 'numpy'
    assert body['configs'][0]['concentration_um'] == 7.25


def test_lied_content_length_rejected():
    async def receive():
        return {'type': 'http.request', 'body': b'{}'}
    request = make_request(receive, [(b'content-length', b'1')])
    with pytest.raises(requests.InvalidBody):
        asyncio.run(requests.campaign_body(request, 'campaign.cancel'))
