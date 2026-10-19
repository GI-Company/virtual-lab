# Package boundaries and development layout

The desktop entry points (`virtual_lab.main` and the launcher) both use
`virtual_lab.gui.shell.main_window`. The former `gui_legacy` window is retired.
All regression tests live in `tests/`; development utilities live in `scripts/`.
Historical codemods and Android patch scripts remain recoverable through Git.

## Scientific and execution layers

Several similarly named packages have different responsibilities:

| Package | Responsibility |
| --- | --- |
| `biological` | Existing RHO numerical state, exposures, constraints and reference analysis. |
| `biology` | Persistent biological objects, versioned expression/maturation mechanisms, continuation and calibration transfer. |
| `compute` | Array operations and numerical backend abstraction. |
| `engines` | Simulation and other execution engines using those operations. |
| `computational` | External computational assays, validated requests, provider adapters and their saved prediction artifacts. |
| `instruments.transport` | Physical device wire protocols, WebSocket channels, packet decoding and discovery. |
| `gateway` | Read-only tool-facing device APIs and adapters above physical transport. |

These boundaries are preserved by the repository cleanup. Moving the names into
one directory would not remove their different contracts. A future biology API
migration needs explicit compatibility and saved-result tests before old import
paths can be retired.

The older proposal provider/context types in `ai.context` and the bounded agent
context assembler in `ai.agent.context` still have different callers. The optional
desktop AI workflow uses Vertex ADK through `ai.runtime_service` and
`ai.vertex_agents`; dormant local MLX functionality has separate opt-in tests.
They have not been merged as part of a repository-layout change.

## Disease programs and viewer assets

`virtual_lab/diseases/rho_p23h/` is the RHO source. Generate a signed program when
needed instead of editing a second committed copy:

```sh
python -m virtual_lab.diseases.packager virtual_lab/diseases/rho_p23h /absolute/path/rho_p23h.vlprogram
```

The packager requires the existing `VLAB_PACKAGER_SK` signing-key configuration.
Generated `.vlprogram` directories are ignored by Git.

Mol* JavaScript/CSS and the reference PDB remain packaged local assets. The
current protein and molecule viewers load them directly, including without an
internet connection; deleting them would break these views.

## Tests and dependency ownership

Install `.[cockpit,dev]` and run `python -m pytest` from the repository root.
Pytest uses importlib mode and a single `tests/` discovery root. Test storage is
isolated with `VIRTUALLAB_DATA_DIR`; offline tests use an in-memory credential
store instead of the operating-system Keychain. Linux CI uses headless Qt;
macOS uses its native Qt platform because WebEngine's offscreen teardown is
unstable on the tested Mac.
Tests are also explicitly excluded from wheels in the build configuration.

`pyproject.toml` owns dependency versions. `requirements-cockpit.txt` is a
compatibility installer for the same extras. The credential-store dependency is
part of the core because both provider imports and cockpit construction need it.

External checks require explicit opt-in:

```sh
VIRTUALLAB_RUN_LIVE_AI_TESTS=1 python -m pytest tests/ai/test_gemini_live.py tests/ai/test_beta_live.py
VIRTUALLAB_RUN_MLX_TESTS=1 python -m pytest tests/hardware
```

The MLX tests require Apple Silicon and the applicable `mlx`/`mlx-lm` packages.
Kotlin interoperability tests skip when Gradle is unavailable and use the
caller's Java configuration. Offline agent-routing tests replace their models
with deterministic test implementations and do not need cloud credentials.

Bundle acceptance uses `python -m scripts.verify_acceptance` (or the shell
wrapper). It generates fixtures in a temporary directory, checks a valid signed
bundle and three tampering cases, then removes its own temporary files. To retain
new snapshots, pass `--output-dir tests/fixtures/vlab`. These are demonstration
bundles using the existing builder's demonstration signing configuration.

Protocol fixture generation is `python -m scripts.generate_protocol_fixtures`.
Optional Gemma benchmark scripts are under `scripts/benchmarks/` and read
`VIRTUALLAB_LOCAL_MODEL` instead of another developer's home directory.


## Researcher-controlled workflow

`core.runtime` starts without importing or constructing the AI runtime. The
optional panel initializes AI only after an explicit enable action. Shared
credentials live in `core.credentials`; the previous AI module is a compatibility
import. The `ai` extra owns both Google AI SDKs.

Human plans and conclusions use validated `domain.research` records saved as
content-addressed, append-only observations. Conclusions carry a saved-plan
reference and explicit verified result references; study import/export checks
those relationships. Human interpretations remain INFERRED, and plans remain
MODEL_ASSUMPTION. See [the manual workflow](manual-research.md).
