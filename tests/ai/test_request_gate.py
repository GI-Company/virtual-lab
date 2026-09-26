import asyncio
import pytest

from google.adk.models.google_llm import Gemini
from virtual_lab.ai.request_gate import GatedGemini, ModelRequestGate


def test_gate_serializes_full_calls(monkeypatch):
    active = 0
    maximum = 0
    starts = []

    async def fake_generate(self, request, stream=False):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        starts.append(asyncio.get_running_loop().time())
        await asyncio.sleep(0.02)
        active -= 1
        yield 'done'

    monkeypatch.setattr(Gemini, 'generate_content_async', fake_generate)
    model = GatedGemini(model='offline-test')
    model._request_gate = ModelRequestGate(0.025)

    async def run():
        async def request():
            return [item async for item in model.generate_content_async(None)]
        return await asyncio.gather(*(request() for _ in range(4)))

    assert asyncio.run(run()) == [['done']] * 4
    assert maximum == 1
    assert all(b - a >= 0.018 for a, b in zip(starts, starts[1:]))


def test_negative_interval_rejected():
    with pytest.raises(ValueError):
        ModelRequestGate(-1)
