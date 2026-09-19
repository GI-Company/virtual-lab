# VirtualLab: Epistemic Research Cockpit

[![Version](https://img.shields.io/badge/version-1.0.0--beta.1-blue.svg)](release_manifest.json)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.14-blue.svg)](pyproject.toml)
[![Platform](https://img.shields.io/badge/platform-macOS%20(Apple%20Silicon)%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)]()
[![Hardware Acceleration](https://img.shields.io/badge/compute-Apple%20Silicon%20Metal%20%2F%20MLX-purple.svg)]()
[![Integrity](https://img.shields.io/badge/provenance-cryptographic%20genesis%20ledger-green.svg)]()

> **"Never assert SIMULATED as MEASURED."**  
> — VirtualLab Epistemic Invariant Rule #1

**VirtualLab** is a high-performance scientific workstation and epistemic research cockpit designed for mechanism-first biological discovery, multi-scale biophysical simulation, and cryptographically verifiable experimental reasoning.

Unlike traditional computational notebooks or black-box ML platforms, VirtualLab enforces **strict epistemic classification**, an **event-sourced causal DAG**, and a **tamper-evident cryptographic ledger**. Every hypothesis, protocol parameter, numerical simulation run, instrument measurement, and scientific decision is permanently captured in a verifiable provenance chain.

---

## Key Architectural Pillars

```
                     ┌───────────────────────────────────────────────┐
                     │          VirtualLab Research Cockpit          │
                     │  (PySide6 Desktop Shell • 9 Workspaces)       │
                     └──────┬───────────────────┬─────────────────┬──┘
                            │                   │                 │
             ┌──────────────┴──────┐  ┌─────────┴───────┐  ┌──────┴──────────────┐
             │ Epistemic AI Agent  │  │ Multi-Backend   │  │ Hardware & Sensor   │
             │   (Gemma 4 MLX &    │  │  Sim Engines    │  │  Transport (v1)     │
             │   Gemini Cloud)     │  │ (Metal RK4/ODE) │  │ (ZeroConf/mDNS/USB) │
             └──────────────┬──────┘  └─────────┬───────┘  └──────┬──────────────┘
                            │                   │                 │
                            └───────────────────┼─────────────────┘
                                                │
                                     ┌──────────▼──────────┐
                                     │   Scientific DAG    │
                                     │  Causality Engine   │
                                     └──────────┬──────────┘
                                                │
                                     ┌──────────▼──────────┐
                                     │   Genesis Ledger    │
                                     │ (SHA-256 / Ed25519) │
                                     └─────────────────────┘
```

### 1. 9-State Epistemic Grounding
VirtualLab fundamentally distinguishes between empirical fact, numerical modeling, and speculative inference. Every data point in the system is tagged with an immutable `EpistemicState`:

| Epistemic State | Description | Example |
| :--- | :--- | :--- |
| `MEASURED` | Direct physical observation; no post-processing beyond A/D conversion | Optical detector voltage, raw camera frame |
| `CALIBRATED` | `MEASURED` signal adjusted by a documented instrument baseline | Dark-field subtracted fluorescence intensity |
| `DERIVED` | Direct calculation from empirical observations | Magnetic field magnitude $\|B\|$ from $(B_x, B_y, B_z)$ |
| `CALCULATED` | Deterministic closed-form formula from constants/inputs | RDKit chemical descriptor, molecular weight |
| `SIMULATED` | Output of a computational numerical solver or trajectory | ODE Runge-Kutta 4th-order concentration trajectory |
| `PREDICTED` | Model projection for conditions not yet experimentally observed | Forecasted cell survival under untested chaperone dose |
| `INFERRED` | Statistical inference or posterior distribution | Parameter estimation via Bayesian Markov Chain Monte Carlo |
| `MODEL_ASSUMPTION` | Boundary condition or assumed parameter input to a model | Assumed basal degradation rate $k_{\text{deg}}$ |
| `UNKNOWN` | Unverified provenance; **strictly quarantined** from publishable results | Unsigned third-party data import |

### 2. Event-Sourced Scientific DAG & Causality
Scientific reasoning is modeled as an immutable, directed acyclic graph (DAG) where child nodes reference valid parent states:
$$\text{Hypothesis} \longrightarrow \text{Protocol} / \text{Prediction} \longrightarrow \text{ExperimentRun} \longrightarrow \text{Observation} \longrightarrow \text{Comparison} \longrightarrow \text{Decision}$$
- **Forward-Only Causality**: Predictions can never reference observations created after them.
- **Type & Unit Checking**: Physical quantities and semantic types are checked for compatibility via `pint`.
- **Reproducibility Invariants**: Re-executing a protocol with identical parameters and random seeds produces identical canonical cryptographic hashes.

### 3. Cryptographic Genesis Ledger & `.vlab` Bundles
- **Append-Only SQLite Ledger**: Stored in `genesis.db` with SQLite triggers rejecting `UPDATE` or `DELETE` operations.
- **Merkle Hash Chaining**: Every event computes its hash from its canonical RFC 8785 JSON representation and the parent event's hash:
  $$\text{Hash}_n = \text{SHA256}(\text{CanonicalJSON}(\text{Event}_n \setminus \{\text{event\_hash}\}) \parallel \text{Hash}_{n-1})$$
- **`.vlab` Research Bundles**: Self-contained cryptographic ZIP containers bundling `genesis.db`, raw artifacts, `manifest.json`, and detached Ed25519 digital signatures (`manifest.sig`).
- **`.vlprogram` Disease Packages**: Standalone signed packages containing biophysical rate equations, state schemas, and initial conditions.

### 4. Local & Cloud Scientific AI Agent
- **Strict Epistemic Protocol**: The reasoning agent cannot mutate working memory directly. It queries system state using `READ` tools and proposes experiments via explicit `PROPOSE` tools.
- **Human-in-the-Loop Approval**: Action proposals (`ExperimentProposal`, `ParameterChanges`, `ParameterSweep`) require scientist verification and sign-off before solver execution.
- **Dual AI Backends**:
  - **Local Apple Silicon MLX**: Native multimodal Gemma 4 Unified models (Text, Vision, Audio) executing with zero data leakage and bounded context budget management.
  - **Cloud Google GenAI**: Integration with Google Gemini (`gemini-3.6-flash`) via `google-genai`.

### 5. Metal GPU-Accelerated Numerical Solvers
- **Apple Silicon Native**: Optimized 4th-order Runge-Kutta (RK4) ODE solver using `mlx.core` on Metal GPUs.
- **Numerical Parity**: Validated against reference NumPy/SciPy backends under the `CERT-1.0-RK4-MLX` numerical certificate.
- **Population Simulations**: Vectorized parameter sweeps and stochastic cell population dynamics running in parallel on unified memory.

### 6. Laboratory Hardware & Edge Sensor Integration
- **Transport Protocol v1**: Framed binary packet decoder for high-throughput instrumentation streaming.
- **ZeroConf / mDNS Discovery**: Automated discovery of laboratory hardware on local subnets.
- **Mobile Edge Sensor Node**: Interoperability with `virtual-lab-mobile` (Android Kotlin client) over WiFi and USB/ADB for external sensor telemetry and camera capture.

---

## Desktop Cockpit: 9 Specialized Workspaces

The PySide6 graphical user interface provides 9 domain-specific workspaces:

1. **World**: Molecular topology, protein target interactions, structural coordinate mapping, and cellular compartment visualizations.
2. **Experiment**: Parameter configuration, boundary conditions, drug exposure profiles, and intervention execution.
3. **Analysis**: High-framerate interactive trajectory plots, phase-space portraits, and dose-response curves powered by PyQtGraph.
4. **Local Research Mode**: Interactive AI workbench for autonomous hypothesis generation, context assembly inspection, and proposal review.
5. **Instruments**: Device status, ZeroConf connection monitor, live camera streaming, optics controls, and exposure calibration.
6. **Evidence**: Tabular repository of all physical observations, assay endpoints, and conflict-detection matrices.
7. **Provenance**: Interactive visual audit of the Genesis Ledger hash chain, event tree, and cryptographic signatures.
8. **Numerical**: Solver benchmarking, MLX Metal vs. NumPy/SciPy tolerance verification, and numerical certificates.
9. **Compare**: Multi-run trajectory overlays, counterfactual simulations, and prediction-vs-observation residual analysis.

---

## Repository Structure

```
VirtualLab/
├── virtual_lab/                  # Core Python package
│   ├── ai/                       # Epistemic AI reasoning framework
│   │   ├── agent/                # Context assembler, agent loop, proposal policies
│   │   ├── memory/               # Hierarchical working memory & projection store
│   │   ├── providers/            # MLX Gemma 4 Unified & Gemini providers
│   │   └── tools.py              # READ / PROPOSE gated scientific tools
│   ├── biological/               # Biological state vectors, exposure & observables
│   ├── cli/                      # Command-line interface utilities
│   │   └── verify.py             # Cryptographic .vlab bundle verifier
│   ├── compute/                  # Compute backends (NumPy, SciPy, MLX abstraction)
│   ├── core/                     # Genesis ledger, canonical JSON, runtime, packaging
│   │   ├── canonical.py          # RFC 8785 deterministic JSON serializer
│   │   ├── ledger.py             # GenesisLedger with SQLite trigger-enforced hash chain
│   │   ├── provenance_export.py  # .vlab verification & provenance explanation
│   │   └── runtime.py            # Unified runtime initialization
│   ├── diseases/                 # Disease programs & .vlprogram packager
│   │   └── rho_p23h/             # Rhodopsin P23H Retinitis Pigmentosa model
│   ├── domain/                   # Epistemics (9 states), state machine DAG, experiment store
│   ├── engines/                  # Metal GPU (MLX) & chemistry ODE solvers
│   ├── gui/                      # PySide6 desktop application & 9 workspaces
│   │   └── shell/                # Main window, theme, workspace manager, system monitor
│   ├── instruments/              # Transport protocol v1, optics, camera, ZeroConf
│   └── matter/                   # Elements, isotopes, molecules, units (pint)
├── protocol/                     # Binary packet protocol schemas and fixtures
├── scripts/                      # Utility scripts (bundle builder, acceptance tests)
│   ├── build_vlab_bundle.py      # Packages experiment into signed .vlab file
│   └── verify_acceptance.sh      # Acceptance test suite for bundle verification
├── tests/                        # Automated test suite (unit, interop, adversarial)
├── pyproject.toml                # Project metadata & dependency declarations
├── release_manifest.json         # Build & verification manifest
├── requirements-cockpit.txt      # Desktop cockpit GUI dependencies
└── start_virtuallab.sh           # macOS launch script
```

---

## Installation & Setup

### Prerequisites
- **Operating System**: macOS (Apple Silicon recommended for MLX GPU acceleration), Linux, or Windows.
- **Python**: Version `>= 3.10` (tested through Python `3.14`).
- **Hardware (Optional)**: Apple Silicon Mac (M1/M2/M3/M4) with 16GB+ unified memory for local MLX model execution.

### 1. Clone the Repository
```bash
git clone https://github.com/your-org/VirtualLab.git
cd VirtualLab
```

### 2. Create and Activate a Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
Install the scientific core:
```bash
pip install -e .
```

To install the desktop cockpit (GUI), chemical informatics (RDKit), and plotting tools:
```bash
pip install -e ".[cockpit,dev]"
```
*(Or install via `pip install -r requirements-cockpit.txt`)*

### 4. Apple Silicon MLX Acceleration (Optional)
On Apple Silicon macOS devices, install Apple MLX for Metal GPU hardware acceleration:
```bash
pip install mlx mlx-lm
```

---

## Running VirtualLab

### Launching the Desktop Cockpit
Using the provided launcher:
```bash
./start_virtuallab.sh
```

Or directly through Python:
```bash
python3 -m virtual_lab.gui.shell.main_window
```

### Configuring AI Backends
VirtualLab operates completely offline with mock/rule-based reasoning. To enable advanced model backends:

- **Google Gemini Cloud API**:
  Set your API key:
  ```bash
  export GEMINI_API_KEY="your-api-key-here"
  ```
- **Local Gemma 4 MLX (Apple Silicon)**:
  Point the loader to your local MLX weights in `~/.lmstudio/models/` or a custom directory.

---

## CLI Tools & Verifiable Workflows

### 1. Verify a `.vlab` Research Bundle
Verify the cryptographic signature, hash chain continuity, zip archive safety, and scientific DAG invariants of any `.vlab` bundle:
```bash
python3 -m virtual_lab.cli.verify pristine.vlab
```
Output:
```text
==================================================
  VIRTUAL LAB: EPISTEMIC PROVENANCE REPORT
==================================================
Bundle: pristine.vlab
Format version: 1.0
Build timestamp (UTC): 2026-09-18T12:00:00Z
Artifacts verified: 2/2 (all SHA-256 match)
Genesis hash chain: VERIFIED (1 events)
Scientific DAG invariants: VALID
Cryptographic signature: VERIFIED (Ed25519)
==================================================
RESULT: BUNDLE PROVENANCE VERIFIED
==================================================
```

### 2. Package an Experiment Workspace
Export an active experiment workspace into an immutable, signed `.vlab` archive:
```bash
python3 scripts/build_vlab_bundle.py ./my_experiment ./my_experiment.vlab
```

### 3. Package a Disease Program (`.vlprogram`)
Package and sign a disease biophysical specification with Ed25519:
```bash
export VLAB_PACKAGER_SK="<hex-encoded-signing-key>"
python3 -c "
from virtual_lab.diseases.packager import package_vlprogram
package_vlprogram('virtual_lab/diseases/rho_p23h', 'rho_p23h.vlprogram')
"
```

---

## Testing & Quality Assurance

VirtualLab features an extensive test suite covering unit functionality, interop protocols, adversarial tampering attacks, and live AI acceptance:

### Run Unit and Domain Tests
```bash
PYTHONPATH=. pytest virtual_lab/test_ledger.py virtual_lab/test_matter.py virtual_lab/test_biological.py
```

### Run Adversarial Cryptographic Verification Tests
Tests defense against zip path traversal attacks, genesis event alterations, artifact byte corruption, and signature tampering:
```bash
bash scripts/verify_acceptance.sh
```

### Run Model Benchmarks (Apple Silicon)
Benchmark local unified memory context consumption and prefill latency:
```bash
python3 run_benchmark.py
```

---

## Epistemic Integrity Rules for Contributors

When developing modules or extending VirtualLab:

1. **Strict Epistemic Attribution**: Never cast or label computational output as `MEASURED`. Only raw hardware or digitized assay readings carry `MEASURED` status.
2. **Deterministic Serialization**: All dictionaries hashed into the Genesis Ledger must use `virtual_lab.core.canonical.canonical_json` (RFC 8785 sorting, whitespace elimination, UTF-8 encoding).
3. **Immutability**: Once an event is written to `GenesisLedger`, it cannot be altered. Corrections must be submitted as new compensating events referencing earlier event IDs.
4. **Agent Boundaries**: AI agents must operate within explicit token budgets and are restricted to read-only queries (`READ`) and formal proposals (`PROPOSE`). Direct workspace mutation by an agent is strictly forbidden.

---

## License

VirtualLab is distributed under a research and scientific license. See [pyproject.toml](pyproject.toml) and repository governance files for full terms.
