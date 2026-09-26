"""Process-local pacing and serialization for Vertex model calls."""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from pydantic import PrivateAttr
from google.adk.models.google_llm import Gemini


class ModelRequestGate:
    """Allow one in-flight call and space starts across a shared model instance."""

    def __init__(self, minimum_interval_s: float = 3.0):
        if minimum_interval_s < 0:
            raise ValueError("minimum_interval_s must be nonnegative")
        self.minimum_interval_s = minimum_interval_s
        self._lock = asyncio.Lock()
        self._next_start = 0.0

    @asynccontextmanager
    async def call_slot(self) -> AsyncIterator[None]:
        async with self._lock:
            delay = self._next_start - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._next_start = time.monotonic() + self.minimum_interval_s
            yield


class GatedGemini(Gemini):
    """Gemini model shared by all agents in one VirtualLab agent system."""

    _request_gate: ModelRequestGate = PrivateAttr(default_factory=ModelRequestGate)

    async def generate_content_async(self, llm_request, stream=False):
        async with self._request_gate.call_slot():
            async for response in super().generate_content_async(llm_request, stream=stream):
                yield response
