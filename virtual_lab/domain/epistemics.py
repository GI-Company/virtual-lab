"""
virtual_lab.domain.epistemics
─────────────────────────────
Canonical 9-state epistemic classification for all results produced,
consumed, or displayed by VirtualLab.

Design notes
────────────
• SIMULATED   — output of a computational trajectory (ODE solution, Monte Carlo)
• MODEL_ASSUMPTION — an assumed parameter or boundary condition *input* to the model,
                     not the trajectory it produces
• CALCULATED  — a pure numerical computation from an explicit, deterministic formula
                (e.g. RDKit descriptor, PRCC coefficient, SHA-256 hash)
• DERIVED     — quantity computed from MEASURED observations (e.g. |B| from Bx, By, Bz)
• CALIBRATED  — MEASURED + known, documented instrument correction factor
• INFERRED    — statistical inference (posterior, regression, classification)
• PREDICTED   — model output for conditions that have not yet been observed
• MEASURED    — direct physical observation, no post-processing beyond A/D conversion
• UNKNOWN     — provenance not established; must not be used for publishable results
"""
from enum import Enum


class EpistemicState(Enum):
    MEASURED         = "MEASURED"
    CALIBRATED       = "CALIBRATED"
    DERIVED          = "DERIVED"
    CALCULATED       = "CALCULATED"
    SIMULATED        = "SIMULATED"
    PREDICTED        = "PREDICTED"
    INFERRED         = "INFERRED"
    MODEL_ASSUMPTION = "MODEL_ASSUMPTION"
    UNKNOWN          = "UNKNOWN"

class QualityState(Enum):
    VALID       = "VALID"
    DEGRADED    = "DEGRADED"
    INCOMPLETE  = "INCOMPLETE"
    INVALID     = "INVALID"
    QUARANTINED = "QUARANTINED"
    UNKNOWN     = "UNKNOWN"
