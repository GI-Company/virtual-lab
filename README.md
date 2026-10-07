# VirtualLab: Epistemic Research Cockpit

VirtualLab connects mechanistic simulations, physical instruments, AlphaGenome predictions, individual AlphaFold DB lookups, and Vertex AI research within one evidence and provenance model. AlphaFold access is on demand; no database mirror or local inference installation is required.

[![Version](https://img.shields.io/badge/version-1.0.0--beta.1-blue.svg)](release_manifest.json)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](pyproject.toml)
[![Platform](https://img.shields.io/badge/platform-macOS%20(Apple%20Silicon)%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)]()
[![Hardware Acceleration](https://img.shields.io/badge/compute-Apple%20Silicon%20Metal%20%2F%20MLX-purple.svg)]()
[![Integrity](https://img.shields.io/badge/provenance-cryptographic%20genesis%20ledger-green.svg)]()

> **"Never assert SIMULATED as MEASURED."**  
> — VirtualLab Epistemic Invariant Rule #1

**VirtualLab** is a high-performance scientific workstation and epistemic research cockpit designed for mechanism-first biological discovery, multi-scale biophysical simulation, and cryptographically verifiable experimental reasoning.

Unlike traditional computational notebooks or black-box ML platforms, VirtualLab enforces **strict epistemic classification**, an **event-sourced causal DAG**, and a **tamper-evident cryptographic ledger**. Recorded experiments and evidence can be linked to a verifiable provenance chain; the source and epistemic status of each result remain explicit.

---

## Key Architectural Pillars

```
                     ┌───────────────────────────────────────────────┐
                     │          VirtualLab Research Cockpit          │
                     │  (PySide6 Desktop Shell • 13 Workspaces)      │
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
  - **Cloud Google GenAI**: Integration with a configured Google Gemini model through Vertex AI.

### 5. Metal GPU-Accelerated Numerical Solvers
- **Apple Silicon Native**: Optimized 4th-order Runge-Kutta (RK4) ODE solver using `mlx.core` on Metal GPUs.
- **Numerical Parity**: Validated against reference NumPy/SciPy backends under the `CERT-1.0-RK4-MLX` numerical certificate.
- **Population Simulations**: Vectorized parameter sweeps and stochastic cell population dynamics running in parallel on unified memory.

### 6. Laboratory Hardware & Edge Sensor Integration
- **Transport Protocol v1**: Framed binary packet decoder for high-throughput instrumentation streaming.
- **ZeroConf / mDNS Discovery**: Automated discovery of laboratory hardware on local subnets.
- **Mobile Edge Sensor Node**: Interoperability with `virtual-lab-mobile` (Android Kotlin client) over WiFi and USB/ADB for external sensor telemetry and camera capture.

### 7. Computational Biology Instruments
- **AlphaGenome**: Runs human hg38 interval, sequence, REF/ALT variant, variant-scoring, and bounded in-silico mutagenesis assays using the official remote API.
- **Biological Context**: Restricts compatible predictions with standardized UBERON, Cell Ontology, or EFO identifiers rather than unstructured tissue labels.
- **AlphaFold DB**: Retrieves metadata and, when explicitly selected, one protein's mmCIF structure and PAE confidence matrix by UniProt accession. Bulk database downloads are not implemented.
- **Prediction Artifacts**: Stores validated inputs, model and client versions, track or score metadata, compressed numerical arrays, limitations, and SHA-256 digests in a verifiable run bundle.
- **Epistemic Boundary**: AlphaGenome and AlphaFold results are recorded as `PREDICTED`, never as physical measurements. Reference structures do not establish mutant structural effects.
- **Vertex Context**: Adds bounded summaries from ledger-verified computational runs to the existing Vertex research workflow. Altered or unanchored artifacts are excluded.

---

## Desktop Cockpit: 13 Top-Level Workspaces

The current PySide6 main window exposes 13 top-level tabs:

1. **Projects**: Create and select studies and experiments; manage study lifecycle.
2. **Biological objects**: Draft biological entities and inspect their links to studies.
3. **RHO reference**: Explore the bundled RHO P23H reference world and molecular views.
4. **Simulation**: Configure and run the implemented mechanistic simulation.
5. **Analysis**: Inspect simulation trajectories and plots.
6. **Calibration**: RNA decay and maturation validation views, each in a nested tab.
7. **Local Research Mode**: Assemble research context and review AI-generated next-step proposals with Vertex credentials.
8. **Instruments**: Inspect connections, sensor streams, camera data, and controls.
9. **Computational Biology**: Run AlphaGenome assays, look up individual AlphaFold DB records, and audit BitVision simulator outputs.
10. **Evidence**: Review saved evidence and its epistemic classification.
11. **Provenance**: Inspect the ledger and verification state.
12. **Numerical**: Inspect solver and numerical validation information.
13. **Compare**: Compare available runs and results.

The RHO view and reference simulation are examples of the current disease program, not evidence that all diseases have validated models. Computational predictions and simulator outputs retain their own labels and do not become `MEASURED` evidence. Signed `.vlab` bundles and `.vlab-study` project archives have distinct trust and security semantics.
---

## Repository Structure

```
virtual-lab/
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
│   ├── computational/            # AlphaGenome/AlphaFold adapters, requests & artifacts
│   ├── core/                     # Genesis ledger, canonical JSON, runtime, packaging
│   │   ├── canonical.py          # RFC 8785 deterministic JSON serializer
│   │   ├── ledger.py             # GenesisLedger with SQLite trigger-enforced hash chain
│   │   ├── provenance_export.py  # .vlab verification & provenance explanation
│   │   └── runtime.py            # Unified runtime initialization
│   ├── diseases/                 # Disease programs & .vlprogram packager
│   │   └── rho_p23h/             # Rhodopsin P23H Retinitis Pigmentosa model
│   ├── domain/                   # Epistemics (9 states), state machine DAG, experiment store
│   ├── engines/                  # Metal GPU (MLX) & chemistry ODE solvers
│   ├── gui/                      # PySide6 desktop application & 13 top-level tabs
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
- **Python**: Version `>= 3.10`; core CI covers 3.10, 3.11, and 3.12.
- **Hardware (Optional)**: Apple Silicon Mac (M1/M2/M3/M4) with 16GB+ unified memory for local MLX model execution.

### 1. Clone the Repository
```bash
git clone https://github.com/GI-Company/virtual-lab.git
cd virtual-lab
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

To enable AlphaGenome, install the computational biology dependencies as well:
```bash
pip install -e ".[cockpit,biology,dev]"
```

AlphaGenome credentials are saved from **Computational Biology → AlphaGenome** using the operating-system credential store. They are not written to source files, experiment manifests, or environment variables. AlphaFold DB metadata needs no API key.

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

### Connecting SensorNode over USB

Connect the phone with USB debugging enabled, then launch the desktop and use
**Instruments → Discover USB Devices → Connect & Launch**. The desktop creates
an `adb reverse` mapping for port 8765 and launches the Android package
`com.aistudio.sensornode.vlsnxz`. The phone connects to `/sensors`, `/control`,
and `/camera` on that port. A phone connecting directly to
`ws://127.0.0.1:8765` requires the reverse mapping; check it with
`adb reverse --list`. For Wi-Fi, use the desktop's LAN address and keep both
devices on a network that permits TCP port 8765 and mDNS discovery.

### Configuring Vertex AI

The desktop agent uses Vertex AI. Choose one authentication mode before
launching VirtualLab:

For express mode, you can paste a key into **Local Research Mode → Vertex
express-mode API key for this session → Use key**. The field is masked, clears
after use, and keeps the key only in the running desktop process. Enter it
again after restarting the app.

```bash
# Vertex AI express mode: set a newly issued Vertex express-mode API key.
export VIRTUALLAB_VERTEX_API_KEY="<key>"
./start_virtuallab.sh
```

```bash
# Google Cloud Vertex AI: use Application Default Credentials.
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT="<project-id>"
export GOOGLE_CLOUD_LOCATION="global"
./start_virtuallab.sh
```

The default model is `gemini-3.5-flash`; override it with
`VIRTUALLAB_VERTEX_MODEL` if needed. Keep keys in your shell or a secret
manager, never in the repository or Android APK. Local Gemma 4 MLX weights
can be configured separately under `~/.lmstudio/models/`.

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

The release regression suite covers projects, computational adapters and artifact checks, core provenance, instruments, protocol, and selected headless GUI tests. GitHub CI runs it on Python 3.10, 3.11, and 3.12 with `QT_QPA_PLATFORM=offscreen`. Kotlin interop runs when Gradle is installed; live cloud, external-service, and MLX/Metal acceptance require separate credentials or hardware and are not included in core CI. [release_manifest.json](release_manifest.json) records the actual Python 3.12 regression and build snapshot.

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

No license has been declared in this repository. The owner must choose and add licensing terms before describing it as open source or inviting redistribution.

## Virtual mass spectrometry (precursor isotope envelope)

For an instrument-free, composition-based prediction, run:

```bash
python3 -m virtual_lab.matter.virtual_mass_spec C6H12O6 --charge 1
```

The JSON output reports centroid m/z, natural-abundance isotope probability,
relative intensity, and probability omitted by the computation cutoff. The
supported formula syntax is an unparenthesized combination of C, H, N, and O,
with at most 200 atoms. Charges 1–5 model protonated `[M+zH]z+` ions. Output
is always `SIMULATED` and deterministic. Isotope masses and representative
abundances follow the [NIST isotope composition tables](https://pml.nist.gov/cgi-bin/Compositions/stand_alone.pl).
Natural abundances are assumptions and vary among samples.

This calculation predicts a precursor isotope envelope from a *known formula*.
It cannot identify an unknown sample, establish purity, predict ionization or
fragmentation, or replace experimental validation. A future virtual MS/MS
capability requires independently validated fragmentation models and reference
spectra; simulated peaks must remain separate from measured evidence.

## Guided autonomous research in the desktop cockpit

In **Local Research Mode**, enter a disease question and select **Research next
step**. The Director receives up to 30 project evidence leads, delegates source
checking to the Research Agent and claim review to the Integrity Agent, then
requests competing falsifiable hypotheses, a discriminating simulation, and a
physical validation study. A Vertex AI credential is required for this workflow.
Catalog entries are leads; the agent must verify their links before using them
as evidence. The workflow does not run instruments or establish clinical efficacy.

The research brief is a single agent episode. It is not a continuous autonomous
literature monitor, and its output still requires scientific review. Research
sessions are scoped to the active experiment when one exists.
