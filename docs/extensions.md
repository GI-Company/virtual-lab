# Instrument and bring-your-own-model adapters v1

The extension boundary distinguishes simulation models, predictive models, advisory AI assistants and acquisition adapters. A common record includes identity/version, inputs/outputs, declared units, epistemic state, source hashes and limitations. Capabilities are explicit; importing a file never grants instrument control or authority to approve a proposal.

## Supported today

| Role | Supported adapter | Output status | Entry point |
|---|---|---|---|
| Simulation | `vlab-ode-v1` data-only JSON equations | SIMULATED | Simulation tab: Import equation model JSON; or CLI |
| Predictor | `vlab-linear-v1` named multivariate linear mapping | PREDICTED | CLI |
| AI assistant | Explicit OpenAI-compatible text endpoint | INFERRED, non-authoritative | CLI |
| Instrument | `vlab-instrument-v1` channel declaration plus CSV | UNKNOWN | CLI |
| Physical gateway | Session-paired loopback WebSockets | Protocol-dependent; physical calibration not validated | Instruments tab |

See runnable examples in `examples/extensions/`. Predictors, CSV instruments and generic assistant endpoints are not yet integrated into the desktop notebook. Gemini's existing optional desktop assistance remains separate. These are initial adapters and contracts, not universal compatibility with every instrument or model format.

## Run in a disposable workspace

From a checkout with core dependencies installed:

```sh
python -m virtual_lab.extensions --workspace /tmp/vlab-extension-demo simulate examples/extensions/decay.json
python -m virtual_lab.extensions --workspace /tmp/vlab-extension-demo predict examples/extensions/linear.json '{"concentration":3}'
python -m virtual_lab.extensions --workspace /tmp/vlab-extension-demo import-csv examples/extensions/instrument.json examples/extensions/signal.csv
```

Each operation saves the actual result under `extension-results/` and appends `EXTENSION_RUN_RECORDED` to `genesis.db`. A crash between artifact writing and ledger appending can leave an unregistered file; it is not treated as a verified completed run. Do not delete historical artifacts or manufacture an execution event to hide this condition.

For a generic assistant, explicitly select the endpoint, model ID and prompt, then add `--allow-network`:

```sh
python -m virtual_lab.extensions --workspace /tmp/vlab-extension-demo assistant http://127.0.0.1:8080/v1/chat/completions your-model 'Critique these assumptions' --allow-network
```

An optional `VIRTUALLAB_BYOM_API_KEY` is used only as an authorization header and is never included in result metadata. HTTPS is required except for loopback HTTP. Redirects and implicit proxies are disabled. Prompts and advisory answers are persisted as research context, so use only material you intend to save and send to that endpoint. The provider model ID is a declaration, not a cryptographic weights fingerprint. There are no execution tools in this adapter.

## Equation models

The JSON manifest declares parameters/bounds/units, states/initial values/constraints, derivatives, version and limitations. Only hour time and micromolar exposure conventions are supported in v1. Expressions allow finite constants, named variables, arithmetic `+ - * /`, unary signs and one-argument `exp`, `log`, `sqrt`. `t` and `exposure` are reserved inputs. Attributes, imports, indexing, comprehensions, arbitrary calls and exponentiation are rejected. AST size and nesting are bounded. No `eval` or `exec` runs imported equations.

The importer pins the original manifest bytes in a content-addressed snapshot and includes both manifest and interpreter hashes in simulation provenance. The shared solver checks finite states, declared bounds and numerical agreement with its DOP853 reference subset. Units must parse, but **equation dimensional consistency is not automatically proven**. A user-supplied equation remains scientifically unvalidated until independently assessed.

Linear predictors preserve their source manifest, named inputs/outputs, units, coefficients and version. Nonfinite inputs/results and inconsistent matrix dimensions are rejected. There is no automatic conversion between requested input units: supply values in the declared units.

General Python, ONNX, safetensors, GGUF and external executable formats are not supported by these data-only adapters. A trusted installed Python extension can be explicitly loaded by name using `load_trusted_extension`; it executes as the user and requires a separate trust assessment. Do not present this as sandboxed untrusted-code execution.

## CSV acquisition

The manifest identifies the operator-declared instrument, manufacturer/model, acquisition/sample/method and ordered channels. Each channel has a name, quantity, unit and axis/signal role. The CSV header must match exactly; rows must be finite numeric data. Limits are 1 MiB and 10,000 samples per file. Original CSV bytes are retained as base64, with SHA-256 and the original channel manifest.

A valid hash shows byte consistency. It does not authenticate the instrument, sample, timestamp, measurement method, calibration or biological interpretation. Thus imported CSV data stays UNKNOWN, never automatically MEASURED or validated. Future vendor adapters should implement the `InstrumentAdapter` protocol and declare actual capabilities and validation evidence.

## Physical transport pairing

The desktop listener is off until explicitly started, and binds only to `127.0.0.1:8765`. In Instruments, enter an approved device ID and a cryptographically random session token of 32–256 characters, pair it, then start the local receiver. Provision the same token securely on the instrument client; never put it in logs, exports or source code. The UI clears its token field after pairing. Pairing is process-local and must be repeated after restart. Rotating a token invalidates existing authenticated connections for that device.

Every `/sensors`, `/camera` and `/control` connection must first send a `CHANNEL_HELLO` containing its exact channel name, device ID and `pairing_token`. Payload identity must match the connection's bound identity. Unpaired sensor/camera/control messages are rejected. Control messages require an explicit paired target; broadcast actuation is disabled. Message/frame size limits and existing frame-size/hash checks still apply.

Existing mobile clients without pairing-token support will be rejected. This protocol has been exercised with test clients, not certified on physical equipment. The token over loopback does not provide end-to-end instrument identity or TLS. Remote operation requires a separately authenticated transport and adapter validation; do not expose this listener by changing its bind address.
