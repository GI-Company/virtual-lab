# Milestone 7 — VirtualLab MCP and ChatGPT integration

A separate read-only MCP adapter is implemented and verified locally. It serves a frozen MS snapshot rather than opening the desktop's live database. The proof of concept uses the user-supplied public BSA reference CSV with 467 peaks. Imported scientific evidence remains UNKNOWN.

This is an MCP protocol prototype, not an installed or published ChatGPT plugin. No ChatGPT account, OpenAI API, tunnel, public HTTP endpoint or paid model was used during local verification. The installer discussed separately has not been built as part of this work.

## Task list

### Limited proof of concept — completed locally

- [x] Add Milestone 7 without replacing the desktop or advancing Milestones 5–6.
- [x] Separate integration package with the optional official Python MCP SDK dependency.
- [x] Six stdio tools with input/output schemas and truthful read-only annotations.
- [x] Independently pin the snapshot catalog and manifest hashes; verify source and normalized bytes on each dataset access.
- [x] Require global MCP enablement, cloud-route permission, export permission, and explicit per-project sharing categories.
- [x] Add default-off MCP Access controls to the full desktop's Privacy page. Saving starts no server or connection.
- [x] Keep spectrum points separate from metadata and summary-report consent.
- [x] Preserve exact decimal spectrum values and bound pagination to 500 peaks per call.
- [x] Exclude source filenames, operator IDs, arbitrary audit-event payloads and raw arrays from summary reports.
- [x] Reject cross-project IDs, changed catalog/artifacts, symlink paths and unsupported laboratory/unspecified data origins.
- [x] Use a real MCP SDK client to perform initialization, tool discovery, calls, denial and revocation checks.
- [x] Verify the public BSA dataset through the adapter; leave the isolated demo policy disabled afterward.
- [x] Preserve snapshot files and original source data; never train, promote a checkpoint or control an instrument.
- [x] Check native Settings rendering/restart and the existing research regression suite.

### Private ChatGPT demonstration — not yet completed

- [ ] Identify the intended ChatGPT workspace and permitted operators.
- [ ] Establish an authorized Secure MCP Tunnel, with the correct workspace association and runtime permissions.
- [ ] Review the exact public-demo categories that may be returned to ChatGPT and enable only those categories.
- [ ] Connect the server in ChatGPT, discover tools and execute the representative BSA query.
- [ ] Record the actual ChatGPT tool selection, arguments, responses and unsupported-request behavior.
- [ ] Disable access and confirm ChatGPT tool calls fail after revocation.

### Laboratory or published integration — later

- [ ] Authenticated accounts, verified project ownership, tenant isolation, scoped OAuth and server-owned writes, aligned with Milestone 6.
- [ ] Data-use authorization and an explicit privacy/export policy for actual laboratory data.
- [ ] Supported spectrum-comparison methods with reproducible analytical definitions and validation.
- [ ] Explicitly authorized persistent report exports through their owning services.
- [ ] Actual INTENT checkpoint/status retrieval and separately governed prospective predictions.
- [ ] Public HTTPS deployment, operational controls, plugin packaging and applicable publication review.
- [ ] Independent laboratory, security, usability and target-platform acceptance.

Training, checkpoint promotion, arbitrary Python execution and instrument control are not exposed by this prototype. `get_intent_status` reports that no INTENT state is included; it does not invent a model status.

## Exposed tools

| Tool | Data returned | Required project category |
| --- | --- | --- |
| `list_projects` | The one shared snapshot project and its experiment IDs | Metadata |
| `get_experiment` | Experiment metadata and dataset IDs | Metadata |
| `verify_dataset` | Source/normalized/manifest hashes and current byte-verification result | Metadata |
| `get_spectrum` | A page of exact decimal m/z and intensity values | Metadata + spectrum |
| `get_report` | An in-memory summary and checksum, without raw arrays or local audit history | Metadata + reports |
| `get_intent_status` | Explicit unavailability of INTENT state in this snapshot | Metadata |

All tools are read-only, non-destructive and bounded to the selected snapshot. They have no network retrieval or arbitrary-path tool arguments. Annotations describe behavior; the server also enforces permissions. Names and research text are untrusted data, not instructions.

The summary has format `virtuallab-mcp-ms-summary`, schema version 1. Its SHA-256 covers the UTF-8 bytes produced by `virtual_lab.pilots.ms_workflow.json_bytes` on the returned object **excluding** `report_sha256`. Its review status is `not_included_in_snapshot`; no live ledger is queried. Historical reprocessing, alteration and review checks are not assumed to pass merely because a snapshot's bytes verify.

## Local setup

From the checkout, install the optional adapter into a suitable environment:

```bash
python -m pip install -e '.[mcp]'
```

Only prepare data you are authorized to use. The helper creates a **new** isolated directory with its own temporary research workspace and private access policy. It does not enable sharing in the normal desktop profile:

```bash
python scripts/build_mcp_demo.py \
  --source /absolute/path/to/public-reference.csv \
  --output /new/isolated/demo-directory \
  --public-reference-confirmed
```

The helper records the snapshot digest and identifiers in `demo.json`. The `public_reference` label is an owner declaration, not independent proof of licensing, provenance or scientific validity. Do not use this helper to relabel proprietary laboratory data.

A local MCP client can launch the adapter with fixed paths and an independently recorded digest:

```bash
python -m virtual_lab.integrations.mcp.server \
  --snapshot /absolute/path/to/demo-directory/snapshot \
  --snapshot-sha256 SHA256_FROM_DEMO_JSON \
  --settings-root /absolute/path/to/demo-directory/access-policy
```

The adapter speaks MCP over stdin/stdout; launching it alone does not connect ChatGPT. It opens no HTTP listener. The publisher's project/experiment IDs are preserved in the catalog, and callers cannot choose a different database or file through a tool argument.

For the **isolated BSA demonstration only**, the local verification driver temporarily enables metadata, reports and spectrum access, exercises the real stdio server, and restores the disabled policy in `finally`:

```bash
python scripts/verify_mcp_demo.py --demo /absolute/path/to/demo-directory
```

That driver expects the supplied 467-peak BSA case and records a local protocol transcript in `mcp-verification.json`. It sends nothing to ChatGPT. Snapshot checksums protect byte consistency relative to the locally pinned digest; they do not authenticate a publisher or replace account authorization.

## Settings and sharing boundary

The Privacy page now has MCP Access, plus Metadata, Reports and Spectrum checkboxes for the active project. All default off. Existing administrator/application/project/experiment rules can deny `mcp`, `cloud` or `exports`. These permissions are independent of the conversational-assistant switch and INTENT permissions. Reading settings does not import the optional MCP SDK.

For an adapter, `--settings-root` must point to the policy repository the owner intends to govern sharing. The frozen snapshot's project ID must have an explicit category grant in that repository. Disabling MCP, cloud routes or exports, removing category consent, or applying a scoped denial affects subsequent calls immediately. This is a local OS-owner permission boundary; anyone who can edit those local files is still trusted. It is not multi-user authentication.

The original source, full manifest and normalized CSV exist inside a private local snapshot folder for verification. They are not exposed as arbitrary downloadable resources. Only the category-allowed projections are returned by tools. A connection alone grants no spectrum access.

Local computation does not make ChatGPT sharing local: any tool result delivered through a future tunnel is transmitted to the connected client. This prototype deliberately avoids enabling or configuring that external connection automatically.

## Connecting to ChatGPT later

Official OpenAI documentation supports an MCP server reached through a public HTTPS endpoint or a Secure MCP Tunnel. The tunnel can reach a local stdio command and does not require an inbound public server port. It does require an associated tunnel, a runtime API key, the relevant Platform permissions and permission to add a custom MCP server in the target ChatGPT workspace. None of those resources were provisioned here.

Use the current official setup rather than copying secrets into a project file:

- [Build an MCP server](https://developers.openai.com/plugins/build/mcp-server)
- [Secure MCP Tunnel: setup, permissions and stdio profiles](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
- [Connect and test the plugin in ChatGPT](https://developers.openai.com/plugins/deploy/connect-chatgpt)

The next end-to-end acceptance query is: “Show the shared BSA experiment, retrieve its spectrum, and check its integrity report.” Completion requires a successful tool call **from ChatGPT**, with recorded evidence. Passing the local SDK tests alone does not satisfy that gate. A public publication would additionally require the deployment and review work documented by OpenAI.

## Reproducible verification

```bash
python -m pytest tests/integrations -q
QT_QPA_PLATFORM=offscreen python -m pytest tests/gui/test_settings_center.py -q
QT_QPA_PLATFORM=cocoa python scripts/verify_settings_center.py --output /new/native-check-directory
```

The protocol test skips when the optional MCP dependency is absent. The local prototype was also exercised in a separate environment with MCP SDK 1.30.0. Dataset bytes, generated snapshots, logs and evidence outputs remain outside Git.
