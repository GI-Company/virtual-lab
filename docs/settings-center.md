# Milestone 4 Settings Center

The full research desktop now has a central Settings Center under the permanent Settings entry. General, AI & Models, INTENT, Monitor, Privacy and Performance pages share a versioned private settings repository. Opening Settings performs no credential lookup, provider activation, inference, training or instrument connection. Saving preferences does not start work.

## Task list and verification scope

- [x] Private, atomic versioned JSON persistence, bounded reads, duplicate/unknown-field rejection and explicit v0-to-v1 migration.
- [x] Six central settings pages with native scrolling and explicit Save / Reload actions.
- [x] Independent persistent assistant, INTENT prediction and INTENT learning switches; all default off.
- [x] Explicit Gemini, Vertex, existing embedded MLX and OpenAI-compatible text adapters, with no alternate-provider fallback.
- [x] Explicit connection tests and compatible-server model discovery, run off the GUI thread.
- [x] OS credential-store integration that rejects plaintext and fallback backends; no keys in preferences, command lines or diagnostic output.
- [x] Distinct embedded, loopback, LAN and cloud policy. LAN/cloud and AI tools default off. Compatible-server redirects and inherited proxies are disabled.
- [x] Intersect administrator, application, project and experiment restrictions before governed operations; lower scopes cannot override a denial.
- [x] Enforce policies at assistant request, tool-policy, INTENT prediction/training/commit and MS report/signed-bundle/study/trajectory export boundaries.
- [x] Shared inference/training job slot; bounded output tokens, worker timeouts, cancellation and process cleanup.
- [x] Local model registry folder, existing MLX path, file-size limit, free-disk gate and active/candidate INTENT checkpoint display.
- [x] Native macOS Settings UI/restart verification and isolated policy/process tests.
- [ ] Live cloud-provider qualification with authorized credentials and an agreed test budget.
- [ ] Real MLX weight-loading/generation qualification for the selected model on target hardware.
- [ ] Windows/Linux desktop and OS credential-store acceptance.
- [ ] Laboratory acceptance and independent scientific validation.

The checked entries describe implemented software behavior, not qualification of every provider/model. No model was downloaded and no genuine experiment outcome was used for training in these checks. Existing institutional reviewer/signature requirements remain unchanged.

## How to use it

1. Open **Settings → AI & Models**. Choose a provider and explicit model identifier. The default compatible endpoint is `http://127.0.0.1:1234/v1`; no server starts automatically.
2. For Gemini or Vertex express mode, enter a credential and select **Store credential**. Vertex also supports an explicit project/location using the SDK's Application Default Credentials. Keys are not imported from environment variables. Compatible-server credentials are scoped to the configured endpoint.
3. For embedded MLX, select an existing absolute model folder containing `config.json`. The adapter uses the existing experimental MLX implementation, with Hugging Face/Transformers offline modes. Model downloads are not provided here.
4. On **Privacy**, permit the required route. An address literal on a private network requires LAN permission; DNS names other than localhost require cloud permission. Localhost is normalized to a loopback literal. This is route classification, not remote-server identity or data-residency attestation.
5. Enable conversational assistance and **Save settings**. **Test connection** sends a fixed `Reply with OK.` prompt only to the saved provider. **Discover server models** queries a compatible server's `/models` endpoint. A successful response establishes a connection, not scientific suitability.
6. Open the optional AI workspace/drawer to send a request. Gemini/Vertex require the optional `ai` dependencies; MLX requires the supported local MLX packages and weights. The managed desktop interface is explicitly text-only and labels responses AI_GENERATED / UNVERIFIED. It does not expose model tools or silently select the legacy ADK orchestration path. Legacy standalone ADK entry points retain their separate configuration; they are outside this desktop policy boundary.
7. Use **Monitor → Cancel / unload model** to stop an active provider worker or INTENT training. Wait for worker exit before changing provider, credentials, resource settings or permissions. Each provider request owns a separate process which exits after completion; there is no persistent loaded model to retain memory. Model warm-start latency is therefore paid per request.

The dedicated offline MS pilot retains its read-only Settings overview and does not acquire cloud/assistant controls. Its INTENT operations and governed exports use the same workspace policy repository.

## Policy and storage

Settings are stored at `settings.json` in the selected VirtualLab workspace, using an atomic file replacement and private file permissions. This is local configuration; the OS account and workspace writer lease remain the trust boundary. It is not authenticated multi-user authorization.

Administrators can supply a read-only-by-OS policy file through `VIRTUALLAB_ADMIN_POLICY`. The file contains only restrictions, such as:

```json
{"cloud": false, "learning": false, "exports": true}
```

Omitted restriction fields permit the application to decide. A false administrator, application, project or experiment permission denies the operation. Invalid configured administrator policy fails closed. Project and experiment restrictions can be edited for the active context on Privacy; they never enable a permission denied above them.

Settings switches are checked at service boundaries, independently of button state. Active assistant requests periodically recheck permissions and discard results on revocation. INTENT rechecks learning permission before committing a worker result. Its ledger-backed project training grants, separately measured outcomes, signed reviews, independent frozen holdout, and manual promotion/rollback still apply. Central settings never turn predictions into observations or grant project training permission.

Governed research exports are MS reports and signed bundles, portable studies, and saved simulation CSVs through their owning services. Low-level formatting functions remain pure byte renderers, not security gateways. Local OS users can still copy their own files.

Provider SDKs load only inside a request worker. Credentials travel to that worker through stdin, with stderr suppressed and provider errors replaced by a generic message. A single job slot prevents managed inference and INTENT training from competing. Local model file size is not a RAM estimate; the monitor and limits do not constitute OS-level memory isolation. No automatic download, automatic model promotion or checkpoint relocation is performed. Existing immutable INTENT checkpoints stay under their original workspace-owned paths.

## Reproducible checks

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/settings tests/gui/test_settings_center.py tests/intent -q
QT_QPA_PLATFORM=cocoa python scripts/verify_settings_center.py --output /new/isolated/verification-directory
```

Local server integration tests bind only a loopback fixture port. Native verification blocks Python network and credential operations and provider SDK imports. The RHO viewer's existing blocked-fetch diagnostic is expected and does not establish structure rendering or external connectivity. On managed macOS sandboxes, Qt/WebEngine IPC and fixture-server binds may need normal local execution permissions.

## MCP Access follow-up

Privacy now also contains default-off MCP Access and per-project Metadata, Reports and Spectrum consent. External MCP results require cloud-route and export permission; assistant and INTENT switches remain independent. Saving never launches the adapter or connects ChatGPT. See the [read-only prototype and complete Milestone 7 task list](virtuallab-mcp-prototype.md).
