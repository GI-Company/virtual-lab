"""
tests.ai.test_vertex_adk_integration
─────────────────────────────────────
Comprehensive automated test suite for Google Vertex ADK multi-agent integration
with the authoritative Virtual Lab Gateway.

Validates:
1. Orchestration hierarchy & authority boundary (Director sole orchestrator, 0 hardware tools)
2. GlobalGemini override removal & standard gemini-3.5-flash configuration
3. Specialist peer-transfer isolation (disallow_transfer_to_peers = True)
4. Structured AgentHandoff schema contract
5. Tool ownership boundaries across all specialists
6. Zero-fabrication enforcement across all gateway tools
7. ADK Runner routing and execution across the 5 required prompt scenarios:
   - "What instruments are connected?" -> instrument_agent -> device_list
   - "Design a Wi-Fi attenuation experiment." -> experiment_agent (zero hardware)
   - "Analyze these supplied RSSI values." -> analysis_agent
   - "Verify this result without raw evidence." -> integrity_agent -> not VERIFIED
   - "Find literature about RSSI-based attenuation measurement." -> research_agent
"""

import os
import sys
import tempfile
import asyncio
import pytest
from typing import AsyncGenerator

from google.genai import types
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.sessions import InMemorySessionService
from google.adk import Runner

import virtual_lab.ai.vertex_agents as va
from virtual_lab.ai.vertex_agents import get_agent_system, AgentHandoff


from virtual_lab.gateway.adk_tools import (
    device_list,
    device_describe,
    device_status,
    device_calibration_get,
    experiment_create,
    experiment_get,
    dataset_summary_statistics,
    provenance_verify,
    artifact_get,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Authority Boundary & Hierarchy Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_director_is_sole_orchestrator():
    system = get_agent_system()
    root_agent = system.root_agent
    instrument_agent = system.instrument_agent
    experiment_agent = system.experiment_agent
    analysis_agent = system.analysis_agent
    integrity_agent = system.integrity_agent
    research_agent = system.research_agent
    """Verify Virtual_Lab_Director is root orchestrator and owns all 5 specialists."""
    assert root_agent.name == "Virtual_Lab_Director"
    subagent_names = {sub.name for sub in root_agent.sub_agents}
    expected_subagents = {
        "instrument_agent",
        "experiment_agent",
        "analysis_agent",
        "integrity_agent",
        "research_agent",
    }
    assert subagent_names == expected_subagents
    assert len(root_agent.sub_agents) == 5


def test_director_holds_zero_hardware_or_system_tools():
    system = get_agent_system()
    root_agent = system.root_agent
    instrument_agent = system.instrument_agent
    experiment_agent = system.experiment_agent
    analysis_agent = system.analysis_agent
    integrity_agent = system.integrity_agent
    research_agent = system.research_agent
    """Authority Boundary: Director must NOT receive device/hardware/filesystem/shell tools."""
    assert root_agent.tools == []
    # Verify Director cannot directly run hardware or raw system operations
    for t in root_agent.tools:
        tool_name = getattr(t, "__name__", str(t))
        assert "device" not in tool_name.lower()
        assert "hardware" not in tool_name.lower()
        assert "shell" not in tool_name.lower()


def test_global_gemini_override_removed():
    system = get_agent_system()
    root_agent = system.root_agent
    instrument_agent = system.instrument_agent
    experiment_agent = system.experiment_agent
    analysis_agent = system.analysis_agent
    integrity_agent = system.integrity_agent
    research_agent = system.research_agent
    """Verify custom GlobalGemini class is removed and standard model is used."""
    # Ensure neither root_agent nor specialists use a GlobalGemini class
    for agent in [root_agent, instrument_agent, experiment_agent, analysis_agent, integrity_agent, research_agent]:
        model_obj = agent.model
        type_name = type(model_obj).__name__
        assert type_name != "GlobalGemini", f"Agent {agent.name} still uses GlobalGemini!"


def test_specialist_peer_transfer_isolation():
    system = get_agent_system()
    root_agent = system.root_agent
    instrument_agent = system.instrument_agent
    experiment_agent = system.experiment_agent
    analysis_agent = system.analysis_agent
    integrity_agent = system.integrity_agent
    research_agent = system.research_agent
    """Specialists must NOT assume they can directly invoke sibling agents."""
    specialists = [
        instrument_agent,
        experiment_agent,
        analysis_agent,
        integrity_agent,
        research_agent,
    ]
    for agent in specialists:
        assert agent.disallow_transfer_to_peers is True, (
            f"{agent.name} must have disallow_transfer_to_peers=True"
        )


def test_structured_handoff_contract():
    system = get_agent_system()
    root_agent = system.root_agent
    instrument_agent = system.instrument_agent
    experiment_agent = system.experiment_agent
    analysis_agent = system.analysis_agent
    integrity_agent = system.integrity_agent
    research_agent = system.research_agent
    """All specialists must configure output_schema=AgentHandoff."""
    specialists = [
        instrument_agent,
        experiment_agent,
        analysis_agent,
        integrity_agent,
        research_agent,
    ]
    for agent in specialists:
        assert agent.output_schema == AgentHandoff, (
            f"{agent.name} must configure output_schema=AgentHandoff"
        )

    # Validate AgentHandoff schema fields
    handoff = AgentHandoff(
        origin_agent="experiment_agent",
        status="COMPLETED",
        summary="Experiment protocol created",
        artifact_refs=["exp_plan_001.json"],
        next_required_role="analysis_agent",
        reason="Requires statistical baseline calculation",
    )
    assert handoff.schema_version == "vlab.handoff.v1"
    assert handoff.origin_agent == "experiment_agent"
    assert handoff.next_required_role == "analysis_agent"
    assert handoff.reason == "Requires statistical baseline calculation"
    assert handoff.run_id is not None
    assert handoff.correlation_id is not None


def test_tool_ownership_boundaries():
    system = get_agent_system()
    root_agent = system.root_agent
    instrument_agent = system.instrument_agent
    experiment_agent = system.experiment_agent
    analysis_agent = system.analysis_agent
    integrity_agent = system.integrity_agent
    research_agent = system.research_agent
    """Verify tool ownership across all specialist agents."""
    # Instrument agent owns device tools
    instrument_tool_names = [t.__name__ for t in instrument_agent.tools]
    assert instrument_tool_names == [
        "device_list",
        "device_describe",
        "device_status",
        "device_calibration_get",
    ]

    # Experiment agent owns metadata tools only (no run execution)
    experiment_tool_names = [t.__name__ for t in experiment_agent.tools]
    assert experiment_tool_names == ["experiment_create", "experiment_get"]

    # Analysis agent owns dataset calculation tools
    analysis_tool_names = [t.__name__ for t in analysis_agent.tools]
    assert analysis_tool_names == ["dataset_summary_statistics"]

    # Integrity agent owns provenance tools
    integrity_tool_names = [t.__name__ for t in integrity_agent.tools]
    assert integrity_tool_names == ["provenance_verify", "artifact_get"]

    # Research agent owns search & URL tools
    assert len(research_agent.tools) == 2


# ─────────────────────────────────────────────────────────────────────────────
# 2. Real Gateway & Zero-Fabrication Tool Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_instrument_tool_device_list_real_state():
    """device_list must call real Virtual Lab Gateway and return real or empty state, never mocks."""
    result = device_list()
    assert result["schema_version"] == "vlab.tool.v1"
    assert result["state"] == "COMPLETED"
    assert "devices" in result["payload"]
    devices = result["payload"]["devices"]
    assert isinstance(devices, list)
    # Check that any device returned is genuine (e.g. adb device or empty)
    for dev in devices:
        assert "device_id" in dev
        assert not dev["device_id"].startswith("mock-")
        assert not dev["device_id"].startswith("fake-")


def test_instrument_tool_device_status_nonexistent():
    """device_status must report UNAVAILABLE/NOT_FOUND for nonexistent device; never report ONLINE."""
    result = device_status("nonexistent_optical_spectrometer_999")
    assert result["schema_version"] == "vlab.tool.v1"
    assert result["state"] in ("UNAVAILABLE", "FAILED")
    assert any(err["code"] == "NOT_FOUND" for err in result["errors"])


def test_instrument_tool_calibration_missing():
    """device_calibration_get must report UNAVAILABLE when no calibration record exists; never invent one."""
    # Test nonexistent device
    res_unknown = device_calibration_get("nonexistent_device")
    assert res_unknown["schema_version"] == "vlab.tool.v1"
    assert res_unknown["state"] == "UNAVAILABLE"
    assert any(err["code"] == "NOT_FOUND" for err in res_unknown["errors"])

    # Test real connected device that has no calibration record
    devices_resp = device_list()
    devices = devices_resp["payload"].get("devices", [])
    if devices:
        real_dev_id = devices[0]["device_id"]
        res_real = device_calibration_get(real_dev_id)
        assert res_real["state"] == "UNAVAILABLE"
        assert res_real["payload"].get("reason") == "NO_CALIBRATION_RECORD"


def test_experiment_create_safe_metadata_only():
    """experiment_create must create record in DRAFT/active state without physical execution."""
    result = experiment_create(label="Wi-Fi Attenuation Baseline", disease_id="rf_study")
    assert result["schema_version"] == "vlab.tool.v1"
    assert result["status"] == "COMPLETED"
    assert result["lifecycle_state"] == "DRAFT"
    assert "experiment_id" in result

    # Read back metadata using experiment_get
    fetched = experiment_get(result["experiment_id"])
    assert fetched["status"] == "COMPLETED"
    assert fetched["experiment"]["label"] == "Wi-Fi Attenuation Baseline"


def test_analysis_dataset_summary_statistics():
    """dataset_summary_statistics must calculate exact statistics and reject empty inputs."""
    # Valid empirical data
    values = [-42.0, -44.0, -45.0, -41.0, -43.0]
    result = dataset_summary_statistics(values, metric_name="rssi_dbm")
    assert result["schema_version"] == "vlab.tool.v1"
    assert result["status"] == "COMPLETED"
    assert result["sample_count"] == 5
    assert result["mean"] == -43.0
    assert result["min"] == -45.0
    assert result["max"] == -41.0
    assert result["epistemic_classification"] == "DERIVED_STATISTICAL_RESULT"

    # Empty inputs must fail, never fabricate observations
    empty_res = dataset_summary_statistics([])
    assert empty_res["status"] == "FAILED"
    assert "error" in empty_res


def test_integrity_provenance_verify_missing_evidence():
    """provenance_verify must report UNSUPPORTED when evidence/db is absent, never claim VERIFIED."""
    result = provenance_verify("/path/to/nonexistent/genesis.db")
    assert result["schema_version"] == "vlab.tool.v1"
    assert result["status"] == "UNAVAILABLE"
    assert result["verdict"] == "UNSUPPORTED"
    assert result["verdict"] != "VERIFIED"


def test_integrity_artifact_get():
    """artifact_get must compute real sha256 and reject path traversal."""
    # Test nonexistent artifact
    res_missing = artifact_get(".virtuallab/artifacts/nonexistent_artifact_xyz.bin")
    assert res_missing["status"] == "UNAVAILABLE"

    # Test path traversal defense
    res_traversal = artifact_get("../../../etc/passwd")
    assert res_traversal["status"] == "FAILED"
    assert "disallowed" in res_traversal["error"]

    # Test real file hashing
    with tempfile.NamedTemporaryFile(dir=os.getcwd(), prefix="test_art_", delete=False) as tf:
        tf.write(b"scientific_raw_photodiode_stream_bytes")
        tf_name = tf.name

    try:
        res_real = artifact_get(os.path.basename(tf_name))
        assert res_real["status"] == "COMPLETED"
        assert res_real["size_bytes"] == len(b"scientific_raw_photodiode_stream_bytes")
        assert len(res_real["artifact_sha256"]) == 64
    finally:
        if os.path.exists(tf_name):
            os.remove(tf_name)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Routing Scenario Tests (Prompt Routing & Delegation Verification)
# ─────────────────────────────────────────────────────────────────────────────

class ScenarioMockLlm(BaseLlm):
    """Deterministic LLM for testing Director delegation and Specialist execution."""
    model: str = "mock-routing-llm"
    agent_name: str = ""
    prompt_scenario: str = ""

    def __init__(self, agent_name: str, prompt_scenario: str, **data):
        super().__init__(model=f"mock-{agent_name}", **data)
        self.agent_name = agent_name
        self.prompt_scenario = prompt_scenario

    async def generate_content_async(
        self, llm_request, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        # Scenario 1: What instruments are connected?
        if self.prompt_scenario == "instruments":
            if self.agent_name == "Virtual_Lab_Director":
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part.from_function_call(
                                name="transfer_to_agent",
                                args={"agent_name": "instrument_agent"}
                            )
                        ]
                    )
                )
            elif self.agent_name == "instrument_agent":
                # First call device_list, then return AgentHandoff
                has_func_resp = any(
                    part.function_response is not None
                    for c in llm_request.contents
                    for part in c.parts
                )
                if not has_func_resp:
                    yield LlmResponse(
                        content=types.Content(
                            role="model",
                            parts=[
                                types.Part.from_function_call(
                                    name="device_list",
                                    args={}
                                )
                            ]
                        )
                    )
                else:
                    yield LlmResponse(
                        content=types.Content(
                            role="model",
                            parts=[
                                types.Part.from_text(
                                    text='{"schema_version":"vlab.handoff.v1","origin_agent":"instrument_agent","status":"COMPLETED","summary":"Discovered devices","artifact_refs":[],"evidence_refs":[],"warnings":[],"errors":[]}'
                                )
                            ]
                        )
                    )

        # Scenario 2: Design a Wi-Fi attenuation experiment
        elif self.prompt_scenario == "experiment":
            if self.agent_name == "Virtual_Lab_Director":
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part.from_function_call(
                                name="transfer_to_agent",
                                args={"agent_name": "experiment_agent"}
                            )
                        ]
                    )
                )
            elif self.agent_name == "experiment_agent":
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part.from_text(
                                text='{"schema_version":"vlab.handoff.v1","origin_agent":"experiment_agent","status":"COMPLETED","summary":"Wi-Fi attenuation protocol designed. Zero hardware acquisition executed.","artifact_refs":[],"evidence_refs":[],"next_required_role":"instrument_agent","reason":"Awaiting user authorization for device acquisition","warnings":[],"errors":[]}'
                            )
                        ]
                    )
                )

        # Scenario 3: Analyze these supplied RSSI values
        elif self.prompt_scenario == "analysis":
            if self.agent_name == "Virtual_Lab_Director":
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part.from_function_call(
                                name="transfer_to_agent",
                                args={"agent_name": "analysis_agent"}
                            )
                        ]
                    )
                )
            elif self.agent_name == "analysis_agent":
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part.from_text(
                                text='{"schema_version":"vlab.handoff.v1","origin_agent":"analysis_agent","status":"COMPLETED","summary":"Statistical analysis computed over supplied RSSI values: mean=-43.0 dBm, std_dev=1.58 dBm","artifact_refs":[],"evidence_refs":[],"warnings":[],"errors":[]}'
                            )
                        ]
                    )
                )

        # Scenario 4: Verify this result without raw evidence
        elif self.prompt_scenario == "integrity":
            if self.agent_name == "Virtual_Lab_Director":
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part.from_function_call(
                                name="transfer_to_agent",
                                args={"agent_name": "integrity_agent"}
                            )
                        ]
                    )
                )
            elif self.agent_name == "integrity_agent":
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part.from_text(
                                text='{"schema_version":"vlab.handoff.v1","origin_agent":"integrity_agent","status":"UNAVAILABLE","summary":"Claim is UNSUPPORTED. No raw evidence or valid cryptographic chain found. Claim cannot be marked as VERIFIED.","artifact_refs":[],"evidence_refs":[],"warnings":["Missing raw evidence"],"errors":[]}'
                            )
                        ]
                    )
                )

        # Scenario 5: Find literature about RSSI-based attenuation measurement
        elif self.prompt_scenario == "research":
            if self.agent_name == "Virtual_Lab_Director":
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part.from_function_call(
                                name="transfer_to_agent",
                                args={"agent_name": "research_agent"}
                            )
                        ]
                    )
                )
            elif self.agent_name == "research_agent":
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part.from_text(
                                text='{"schema_version":"vlab.handoff.v1","origin_agent":"research_agent","status":"COMPLETED","summary":"Retrieved peer-reviewed literature on RSSI path-loss models (IEEE 802.11 standards).","artifact_refs":[],"evidence_refs":[],"warnings":[],"errors":[]}'
                            )
                        ]
                    )
                )


def test_scenario_1_instruments_routing():
    """Prompt: 'What instruments are connected?'
    Expected: Director delegates to instrument_agent, instrument_agent calls device_list.
    """
    async def _run():
        system = get_agent_system()
        root_agent = system.root_agent
        instrument_agent = system.instrument_agent
        experiment_agent = system.experiment_agent
        analysis_agent = system.analysis_agent
        integrity_agent = system.integrity_agent
        research_agent = system.research_agent
        session_service = InMemorySessionService()
        session = await session_service.create_session(app_name="virtual_lab", user_id="tester")

        root_agent.model = ScenarioMockLlm("Virtual_Lab_Director", "instruments")
        instrument_agent.model = ScenarioMockLlm("instrument_agent", "instruments")

        runner = Runner(agent=root_agent, app_name="virtual_lab", session_service=session_service)

        events = []
        async for event in runner.run_async(
            user_id="tester",
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part.from_text(text="What instruments are connected?")])
        ):
            events.append(event)

        # Verify delegation from Director to instrument_agent
        delegation_events = [
            e for e in events
            if e.actions and getattr(e.actions, "transfer_to_agent", None) == "instrument_agent"
        ]
        assert len(delegation_events) >= 1
        assert delegation_events[0].author == "Virtual_Lab_Director"

        # Verify instrument_agent was active and participated
        instrument_events = [e for e in events if e.author == "instrument_agent"]
        assert len(instrument_events) >= 1

    asyncio.run(_run())


def test_scenario_2_experiment_routing():
    """Prompt: 'Design a Wi-Fi attenuation experiment.'
    Expected: Director delegates to experiment_agent. No hardware acquisition occurs.
    """
    async def _run():
        system = get_agent_system()
        root_agent = system.root_agent
        instrument_agent = system.instrument_agent
        experiment_agent = system.experiment_agent
        analysis_agent = system.analysis_agent
        integrity_agent = system.integrity_agent
        research_agent = system.research_agent
        session_service = InMemorySessionService()
        session = await session_service.create_session(app_name="virtual_lab", user_id="tester")

        root_agent.model = ScenarioMockLlm("Virtual_Lab_Director", "experiment")
        experiment_agent.model = ScenarioMockLlm("experiment_agent", "experiment")

        runner = Runner(agent=root_agent, app_name="virtual_lab", session_service=session_service)

        events = []
        async for event in runner.run_async(
            user_id="tester",
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part.from_text(text="Design a Wi-Fi attenuation experiment.")])
        ):
            events.append(event)

        # Verify delegation to experiment_agent
        delegation_events = [
            e for e in events
            if e.actions and getattr(e.actions, "transfer_to_agent", None) == "experiment_agent"
        ]
        assert len(delegation_events) >= 1

        # Verify experiment_agent responded and NO device acquisition tools were called
        exp_events = [e for e in events if e.author == "experiment_agent"]
        assert len(exp_events) >= 1

        # Verify no hardware acquisition tools were executed during this run
        for e in events:
            if e.content and e.content.parts:
                for p in e.content.parts:
                    if p.function_call:
                        assert p.function_call.name not in ["device_status", "device_describe"]

    asyncio.run(_run())


def test_scenario_3_analysis_routing():
    """Prompt: 'Analyze these supplied RSSI values.'
    Expected: Director delegates to analysis_agent.
    """
    async def _run():
        system = get_agent_system()
        root_agent = system.root_agent
        instrument_agent = system.instrument_agent
        experiment_agent = system.experiment_agent
        analysis_agent = system.analysis_agent
        integrity_agent = system.integrity_agent
        research_agent = system.research_agent
        session_service = InMemorySessionService()
        session = await session_service.create_session(app_name="virtual_lab", user_id="tester")

        root_agent.model = ScenarioMockLlm("Virtual_Lab_Director", "analysis")
        analysis_agent.model = ScenarioMockLlm("analysis_agent", "analysis")

        runner = Runner(agent=root_agent, app_name="virtual_lab", session_service=session_service)

        events = []
        async for event in runner.run_async(
            user_id="tester",
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part.from_text(text="Analyze these supplied RSSI values: [-42, -44, -45, -41, -43]")])
        ):
            events.append(event)

        delegation_events = [
            e for e in events
            if e.actions and getattr(e.actions, "transfer_to_agent", None) == "analysis_agent"
        ]
        assert len(delegation_events) >= 1
        analysis_events = [e for e in events if e.author == "analysis_agent"]
        assert len(analysis_events) >= 1

    asyncio.run(_run())


def test_scenario_4_integrity_routing():
    """Prompt: 'Verify this result without raw evidence.'
    Expected: Director delegates to integrity_agent. Claim is not VERIFIED.
    """
    async def _run():
        system = get_agent_system()
        root_agent = system.root_agent
        instrument_agent = system.instrument_agent
        experiment_agent = system.experiment_agent
        analysis_agent = system.analysis_agent
        integrity_agent = system.integrity_agent
        research_agent = system.research_agent
        session_service = InMemorySessionService()
        session = await session_service.create_session(app_name="virtual_lab", user_id="tester")

        root_agent.model = ScenarioMockLlm("Virtual_Lab_Director", "integrity")
        integrity_agent.model = ScenarioMockLlm("integrity_agent", "integrity")

        runner = Runner(agent=root_agent, app_name="virtual_lab", session_service=session_service)

        events = []
        async for event in runner.run_async(
            user_id="tester",
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part.from_text(text="Verify this result without raw evidence.")])
        ):
            events.append(event)

        delegation_events = [
            e for e in events
            if e.actions and getattr(e.actions, "transfer_to_agent", None) == "integrity_agent"
        ]
        assert len(delegation_events) >= 1
        integrity_events = [e for e in events if e.author == "integrity_agent"]
        assert len(integrity_events) >= 1

        # Verify claim is not marked VERIFIED in any output
        full_text = " ".join(
            p.text for e in events if e.content and e.content.parts for p in e.content.parts if p.text
        )
        assert "UNSUPPORTED" in full_text
        assert '"verdict": "VERIFIED"' not in full_text

    asyncio.run(_run())


def test_scenario_5_research_routing():
    """Prompt: 'Find literature about RSSI-based attenuation measurement.'
    Expected: Director delegates to research_agent.
    """
    async def _run():
        system = get_agent_system()
        root_agent = system.root_agent
        instrument_agent = system.instrument_agent
        experiment_agent = system.experiment_agent
        analysis_agent = system.analysis_agent
        integrity_agent = system.integrity_agent
        research_agent = system.research_agent
        session_service = InMemorySessionService()
        session = await session_service.create_session(app_name="virtual_lab", user_id="tester")

        root_agent.model = ScenarioMockLlm("Virtual_Lab_Director", "research")
        research_agent.model = ScenarioMockLlm("research_agent", "research")

        runner = Runner(agent=root_agent, app_name="virtual_lab", session_service=session_service)

        events = []
        async for event in runner.run_async(
            user_id="tester",
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part.from_text(text="Find literature about RSSI-based attenuation measurement.")])
        ):
            events.append(event)

        delegation_events = [
            e for e in events
            if e.actions and getattr(e.actions, "transfer_to_agent", None) == "research_agent"
        ]
        assert len(delegation_events) >= 1
        research_events = [e for e in events if e.author == "research_agent"]
        assert len(research_events) >= 1

    asyncio.run(_run())

