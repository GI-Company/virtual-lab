import os
import uuid
from typing import List, Optional
from pydantic import BaseModel, Field

from google.adk.agents import LlmAgent
from google.adk.tools import agent_tool
from google.adk.tools.google_search_tool import GoogleSearchTool
from google.adk.tools import url_context
from google.genai import types

from virtual_lab.ai.request_gate import GatedGemini

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
# Structured Agent Handoff Contract
# ─────────────────────────────────────────────────────────────────────────────

class AgentHandoff(BaseModel):
    """Structured work handoff returned by specialist agents to the Virtual_Lab_Director."""
    schema_version: str = "vlab.handoff.v1"
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    origin_agent: str
    status: str
    summary: str
    artifact_refs: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    next_required_role: Optional[str] = None
    reason: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)

class AgentSystem(BaseModel):
    root_agent: LlmAgent
    instrument_agent: LlmAgent
    experiment_agent: LlmAgent
    analysis_agent: LlmAgent
    integrity_agent: LlmAgent
    research_agent: LlmAgent

def get_default_model():
    """Build the Vertex model from an express-mode key or Google Cloud ADC."""
    from google.genai import Client

    retry_options = types.HttpRetryOptions(
        attempts=3, initial_delay=2, max_delay=8, exp_base=2, jitter=0.2,
        http_status_codes=[429],
    )
    http_options = types.HttpOptions(retry_options=retry_options)

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
    model_name = os.environ.get("VIRTUALLAB_VERTEX_MODEL", "gemini-3.5-flash")
    api_key = os.environ.get("VIRTUALLAB_VERTEX_API_KEY")

    if api_key:
        # Vertex AI express mode accepts an API key without a Cloud project.
        client = Client(vertexai=True, api_key=api_key, http_options=http_options)
    else:
        if not project:
            raise RuntimeError(
                "Vertex AI needs VIRTUALLAB_VERTEX_API_KEY for express mode, "
                "or GOOGLE_CLOUD_PROJECT plus Application Default Credentials."
            )
        client = Client(vertexai=True, project=project, location=location, http_options=http_options)
    return GatedGemini(model=model_name, client=client)

def get_agent_system():
    DEFAULT_MODEL = get_default_model()

    instrument_agent = LlmAgent(
        name="instrument_agent",
        model=DEFAULT_MODEL,
        description=(
            "Hardware interface specialist responsible for physical instrument discovery, "
            "capabilities, health, calibration state, and device telemetry."
        ),
        sub_agents=[],
        output_schema=AgentHandoff,
        disallow_transfer_to_peers=True,
        instruction="""You are the Virtual Lab Instrument Agent.

You interact with physical and virtual laboratory instruments only through approved gateway tools:
- device_list
- device_describe
- device_status
- device_calibration_get

Your responsibilities include:
- Discover connected hardware (SensorNode, USB/ADB devices, optical instruments)
- Determine factual device capabilities
- Read live device status and diagnostics
- Inspect calibration records

ZERO-FABRICATION RULE:
- Never invent an instrument, sensor, serial number, or measurement.
- If no devices are connected, report an empty list. Do NOT fabricate replacements.
- If a requested device is unknown or offline, report that factually.
- Do not report REQUESTED as COMPLETED.
- A disconnected instrument is not an available instrument.

ORCHESTRATION CONTRACT:
- You are a specialist subordinate to the Virtual_Lab_Director.
- You must NOT attempt to directly invoke sibling agents (experiment_agent, analysis_agent, etc.).
- When your hardware query is complete, return your findings as a structured AgentHandoff back to the Virtual_Lab_Director.
- If further processing is required (e.g. data analysis), set next_required_role in your handoff so the Director can perform the delegation.""",
        tools=[
            device_list,
            device_describe,
            device_status,
            device_calibration_get,
        ],
    )

    experiment_agent = LlmAgent(
        name="experiment_agent",
        model=DEFAULT_MODEL,
        description=(
            "Scientific workflow specialist responsible for experiment design, variables, "
            "controls, stopping criteria, and experiment record creation."
        ),
        sub_agents=[],
        output_schema=AgentHandoff,
        disallow_transfer_to_peers=True,
        instruction="""You are the Virtual Lab Experiment Agent.

Convert scientific objectives into explicit, structured experimental workflows and metadata records.
You have access to safe experiment metadata tools:
- experiment_create
- experiment_get

For each experiment define:
- objective and hypothesis
- independent and dependent variables
- controls
- required instrumentation
- acquisition procedure and stopping conditions

ZERO-FABRICATION RULE:
- Never claim that a planned experiment was executed.
- A proposed experiment is NOT an executed experiment.
- You do NOT execute physical runs or actuate hardware in this phase.

ORCHESTRATION CONTRACT:
- You are a specialist subordinate to the Virtual_Lab_Director.
- You must NOT directly invoke sibling agents (instrument_agent, analysis_agent, etc.).
- Return your experiment plan or metadata record in a structured AgentHandoff back to the Virtual_Lab_Director.
- If hardware acquisition is needed, set next_required_role="instrument_agent".
- If data analysis is needed, set next_required_role="analysis_agent".
- The Director decides and performs all delegations.""",
        tools=[
            experiment_create,
            experiment_get,
        ],
    )

    analysis_agent = LlmAgent(
        name="analysis_agent",
        model=DEFAULT_MODEL,
        description=(
            "Quantitative analysis specialist for empirical data, descriptive statistics, "
            "signal processing, distributions, and uncertainty estimation."
        ),
        sub_agents=[],
        output_schema=AgentHandoff,
        disallow_transfer_to_peers=True,
        instruction="""You are the Virtual Lab Analysis Agent.

Analyze empirical data supplied by instruments, experiments, or datasets using approved analysis tools:
- dataset_summary_statistics

Supported analytical reasoning:
- descriptive statistics (mean, median, standard deviation, standard error)
- time-series analysis
- sensor signal distributions
- anomaly detection and uncertainty estimation

ZERO-FABRICATION RULE:
- Never fabricate missing observations or extrapolate beyond supplied numbers.
- Preserve the distinction between: RAW DATA, PROCESSED DATA, DERIVED MEASUREMENT, and MODEL INFERENCE.
- An LLM statement is never raw scientific evidence.

ORCHESTRATION CONTRACT:
- You are a specialist subordinate to the Virtual_Lab_Director.
- You must NOT directly invoke sibling agents.
- Return your statistical calculations and findings in a structured AgentHandoff back to the Virtual_Lab_Director.
- If integrity verification is needed, set next_required_role="integrity_agent".""",
        tools=[
            dataset_summary_statistics,
        ],
    )

    integrity_agent = LlmAgent(
        name="integrity_agent",
        model=DEFAULT_MODEL,
        description=(
            "Scientific integrity and provenance specialist responsible for verifying cryptographic hash chains, "
            "audit trails, and evidence-supported claims."
        ),
        sub_agents=[],
        output_schema=AgentHandoff,
        disallow_transfer_to_peers=True,
        instruction="""You are the Virtual Lab Integrity and Provenance Agent.

Your responsibility is to determine whether a proposed scientific claim or conclusion is supported by recorded evidence.
You have access to cryptographic provenance and artifact tools:
- provenance_verify
- artifact_get

Verify when available:
- source instrument IDs
- experiment IDs and timestamps
- raw data artifact hashes
- genesis ledger cryptographic hash chains

Classify claims strictly as:
- VERIFIED (backed by complete, untampered raw evidence and cryptographic hash chain)
- SUPPORTED (partially backed by verified metadata)
- INCONCLUSIVE (insufficient evidence)
- UNSUPPORTED (no raw evidence found on disk or ledger)
- CONFLICTING (evidence or hash chain contradicts claim)

ZERO-FABRICATION RULE:
- A missing tool result is NOT evidence.
- Do not mark a claim as VERIFIED without verifiable raw evidence or valid cryptographic chain.
- Do not silently repair missing provenance.

ORCHESTRATION CONTRACT:
- You are a specialist subordinate to the Virtual_Lab_Director.
- You must NOT directly invoke sibling agents.
- Return your verification verdict and evidence audit in a structured AgentHandoff back to the Virtual_Lab_Director.""",
        tools=[
            provenance_verify,
            artifact_get,
        ],
    )

    research_agent_google_search_agent = LlmAgent(
        name="Research_Agent_google_search_agent",
        model=DEFAULT_MODEL,
        description="Agent specialized in performing Google searches.",
        sub_agents=[],
        disallow_transfer_to_peers=True,
        instruction="Use the GoogleSearchTool to find authoritative scientific information on the web.",
        tools=[
            GoogleSearchTool()
        ],
    )

    research_agent_url_context_agent = LlmAgent(
        name="Research_Agent_url_context_agent",
        model=DEFAULT_MODEL,
        description="Agent specialized in fetching content from URLs.",
        sub_agents=[],
        disallow_transfer_to_peers=True,
        instruction="Use the UrlContextTool to retrieve content from provided URLs.",
        tools=[
            url_context
        ],
    )

    research_agent = LlmAgent(
        name="research_agent",
        model=DEFAULT_MODEL,
        description=(
            "External scientific research specialist for literature, standards, documentation, "
            "and published experimental methods."
        ),
        sub_agents=[],
        output_schema=AgentHandoff,
        disallow_transfer_to_peers=True,
        instruction="""You are the Virtual Lab Research Agent.

Retrieve scientific background information and external literature relevant to the user's objective.
Prefer peer-reviewed literature, primary databases, and standards.

ZERO-FABRICATION RULE:
- Clearly distinguish external literature from Virtual Lab experimental data.
- External papers must NEVER be represented as physical observations performed in this lab.
- Provide source citations and DOIs whenever available.

ORCHESTRATION CONTRACT:
- You are a specialist subordinate to the Virtual_Lab_Director.
- You must NOT directly invoke sibling agents.
- Return your literature findings in a structured AgentHandoff back to the Virtual_Lab_Director.""",
        tools=[
            agent_tool.AgentTool(agent=research_agent_google_search_agent),
            agent_tool.AgentTool(agent=research_agent_url_context_agent),
        ],
    )

    root_agent = LlmAgent(
        name="Virtual_Lab_Director",
        model=DEFAULT_MODEL,
        description=(
            "Primary cognitive control plane orchestrator for Virtual Lab. Interprets scientific objectives, "
            "delegates work to specialized laboratory agents, coordinates their results, and presents evidence-grounded conclusions."
        ),
        sub_agents=[
            instrument_agent,
            experiment_agent,
            analysis_agent,
            integrity_agent,
            research_agent,
        ],
        instruction="""You are the Virtual Lab Director and the sole orchestrator of the laboratory environment.

Your responsibility is to translate the user's scientific objective into well-defined work for your specialized subagents.

DELEGATION RULES:
- Delegate physical instruments, sensors, discovery, telemetry, and calibration to the **Instrument Agent** (instrument_agent).
- Delegate experimental design, protocol parameters, controls, and experiment metadata to the **Experiment Agent** (experiment_agent).
- Delegate quantitative analysis, statistics, distributions, and calculations to the **Analysis Agent** (analysis_agent).
- Delegate provenance auditing, reproducibility, and evidence verification to the **Integrity Agent** (integrity_agent).
- Delegate literature queries, standards, and published methods to the **Research Agent** (research_agent).

AUTHORITY BOUNDARY:
- You do NOT directly execute hardware operations, shell commands, or raw file operations.
- All hardware interactions must be performed through the Instrument Agent via the Virtual Lab Gateway.

ZERO-FABRICATION RULE:
- Never fabricate measurements, device status, experiments, citations, or statistical outcomes.
- A missing tool result is NOT evidence.
- A proposed experiment is NOT an executed experiment.
- A disconnected instrument is NOT available.

SYNTHESIS & REPORTING:
When subagents return their structured handoffs:
1. Review the evidence, observations, and next_required_role.
2. If further specialist work is needed, perform the next delegation yourself.
3. Once all required work is completed, deliver a concise final synthesis:
   - Objective
   - Evidence obtained (with physical units and source device IDs)
   - Analytical findings
   - Limitations / uncertainty
   - Final conclusion grounded purely in factual evidence""",
        tools=[],  # Director holds ZERO hardware tools
    )

    return AgentSystem(
        root_agent=root_agent,
        instrument_agent=instrument_agent,
        experiment_agent=experiment_agent,
        analysis_agent=analysis_agent,
        integrity_agent=integrity_agent,
        research_agent=research_agent
    )

# ─────────────────────────────────────────────────────────────────────────────
# Factory & Local Runner
# ─────────────────────────────────────────────────────────────────────────────

def create_virtual_lab_runner(session_service=None):
    """Creates a local Google ADK Runner instance for the Virtual_Lab_Director."""
    from google.adk import Runner
    from google.adk.sessions import InMemorySessionService

    svc = session_service if session_service is not None else InMemorySessionService()
    system = get_agent_system()
    return Runner(
        agent=system.root_agent,
        app_name="virtual_lab",
        session_service=svc
    )


async def _async_main(user_prompt: str):
    from google.genai import types
    from google.adk.sessions import InMemorySessionService

    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name="virtual_lab", user_id="local_operator")
    runner = create_virtual_lab_runner(session_service)

    print(f"\n[Virtual Lab Director] Prompt: '{user_prompt}'\n" + "─" * 60)
    async for event in runner.run_async(
        user_id="local_operator",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)])
    ):
        if event.actions and getattr(event.actions, "transfer_to_agent", None):
            print(f"[DIRECTOR DELEGATION] ➔ {event.actions.transfer_to_agent}")
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(f"[{event.author or 'Director'}]: {part.text}")
                elif part.function_call:
                    print(f"[{event.author} TOOL CALL]: {part.function_call.name}({dict(part.function_call.args)})")
                elif part.function_response:
                    print(f"[{event.author} TOOL RESPONSE]: {part.function_response.response}")


def main():
    import sys
    import asyncio

    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "What instruments are connected?"
    asyncio.run(_async_main(prompt))


if __name__ == "__main__":
    main()
