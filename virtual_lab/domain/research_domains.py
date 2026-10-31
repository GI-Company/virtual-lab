"""Shared presentation registry. A discipline never changes evidence semantics."""

from dataclasses import dataclass
from enum import Enum


class Availability(str, Enum):
    ENABLED = "enabled"
    EXPERIMENTAL = "experimental"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class Tool:
    id: str
    title: str
    status: Availability = Availability.ENABLED
    note: str = ""


@dataclass(frozen=True)
class Domain:
    id: str
    title: str
    icon: str
    description: str
    tools: tuple[str, ...]
    default_tool: str = "projects"


TOOLS = {
    tool.id: tool
    for tool in (
        Tool("projects", "Experiments & notebook"),
        Tool(
            "ms_workflow",
            "MS Workflow",
            note="Preserved CSV spectra, workflow checks and hashed reports; evidence UNKNOWN.",
        ),
        Tool(
            "intent",
            "INTENT",
            Availability.EXPERIMENTAL,
            "Local numerical predictions and reviewed learning; off by default.",
        ),
        Tool(
            "biological",
            "Biological objects",
            Availability.EXPERIMENTAL,
            "Modeled biological systems; not experimental validation.",
        ),
        Tool(
            "rho_reference",
            "RHO reference",
            Availability.EXPERIMENTAL,
            "Installed reference visualization, not a general protein-structure service.",
        ),
        Tool(
            "simulation",
            "Simulation",
            Availability.EXPERIMENTAL,
            "Assumed numerical models produce SIMULATED evidence.",
        ),
        Tool("analysis", "Analysis"),
        Tool("calibration", "Calibration", Availability.EXPERIMENTAL),
        Tool(
            "assistant",
            "AI assistance",
            Availability.EXPERIMENTAL,
            "Optional provider configuration and separate activation required.",
        ),
        Tool(
            "instruments",
            "Instruments & sensors",
            Availability.EXPERIMENTAL,
            "Explicit listener activation and supported hardware required.",
        ),
        Tool(
            "computational",
            "Computational biology",
            Availability.EXPERIMENTAL,
            "Assay-specific providers, accounts or artifacts may be required.",
        ),
        Tool("evidence", "Evidence"),
        Tool("provenance", "Provenance"),
        Tool("numerical", "Numerical checks"),
        Tool("compare", "Compare simulations"),
        Tool(
            "ms_identification",
            "MS/MS compound identification",
            Availability.UNAVAILABLE,
            "Not implemented by the CSV MS pilot.",
        ),
    )
}

COMMON = ("projects", "intent", "provenance")
DOMAINS = {
    domain.id: domain
    for domain in (
        Domain(
            "mass_spectrometry",
            "Mass Spectrometry",
            "MS",
            "Spectra, preserved data and MS workflow reports",
            COMMON + ("ms_workflow", "ms_identification"),
            "ms_workflow",
        ),
        Domain(
            "molecular_biology",
            "Molecular Biology",
            "MB",
            "Biological models and installed reference structures",
            COMMON + ("biological", "rho_reference"),
        ),
        Domain(
            "computational_biology",
            "Computational Biology",
            "CB",
            "Computational assays and modeled experiments",
            COMMON + ("computational", "simulation", "analysis"),
        ),
        Domain(
            "physics_simulation",
            "Physics & Simulation",
            "PS",
            "Numerical experiments and calibration",
            COMMON + ("simulation", "analysis", "calibration", "numerical", "compare"),
        ),
        Domain(
            "instruments_sensors",
            "Instruments & Sensors",
            "IS",
            "Supported hardware and measurement acquisition",
            COMMON + ("instruments",),
        ),
        Domain(
            "data_analysis",
            "Data & Research Analysis",
            "DA",
            "Evidence, comparison and research interpretation",
            COMMON + ("analysis", "evidence", "compare", "numerical"),
        ),
        Domain(
            "general",
            "General research",
            "GR",
            "Existing and multidisciplinary projects; choose a discipline when ready",
            COMMON + ("simulation", "analysis", "evidence", "compare"),
        ),
    )
}


def domain_by_id(domain_id):
    if domain_id not in DOMAINS:
        raise ValueError("Choose a supported research discipline")
    return DOMAINS[domain_id]


def tool_availability(tool_id, installed_tools):
    tool = TOOLS[tool_id]
    return tool.status if tool_id in installed_tools else Availability.UNAVAILABLE


@dataclass(frozen=True)
class PresentationProfile:
    id: str
    title: str
    introduction: str


PROFILES = {
    "research": PresentationProfile(
        "research",
        "VirtualLab Research",
        "Choose a discipline, open a project and continue your research.",
    ),
    "academia": PresentationProfile(
        "academia",
        "VirtualLab Academia",
        "Choose a discipline to plan, explore and document a study. Modeled results retain their scientific labels.",
    ),
}
