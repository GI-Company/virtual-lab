# Read-only research service qualification

This document describes the default read-only mode. An explicitly enabled
[private campaign service](private-research-campaigns.md) now adds bounded custom
numerical execution, separate default-off grants and synthetic qualification.
Without `--enable-campaigns`, the routes and mutation rejection below still apply.

This milestone adds a private HTTP adapter to the existing Python `ResearchEngine`. It has been qualified locally against a new synthetic instance. It has **not** been deployed, connected to GIC accounts, installed in ChatGPT, or paired with the desktop UI. Three independent HTTP clients in the qualification stand in for those future interfaces. They do not establish integration with the actual products.

Design reference: [GIC integration blueprint at the reviewed PR head](https://github.com/GI-Company/GiC/blob/a65e68287b6077d1aa20eae0cbcdb47c7960d427/docs/virtual-lab-shared-engine-integration.md), subsequently merged in PR #15. No website files, paid-account policy, Stripe configuration, public demonstration, or production database were changed by this Python service milestone.

## Implemented boundary

- One dedicated thread constructs, reads and closes the engine. HTTP handlers never open SQLite. The workspace lease prevents a second owner. Only a deliberately selected existing instance can start; no desktop workspace is discovered or uploaded.
- Short-lived RS256 bearer tokens require a pinned HTTPS issuer, service audience, signing key ID, subject, issue/expiry times and token ID. The server holds public verification keys only. It does not follow token-supplied key URLs or infer signing algorithms from tokens. Maximum token lifetime is 15 minutes.
- An operator-owned, strict JSON policy binds the instance, project to tenant, account membership, research entitlement and independent metadata/report/spectrum/change permissions. All grants default off. Claims such as `subscription`, `surface` and `project_id` do not grant authority. The policy is loaded for each dispatch and rechecked before returning scoped data. Membership or token-ID revocation takes effect on new calls, including queued work. Revocation cannot withdraw already returned bytes.
- Existing Settings export/cloud restrictions also apply at administrator, project and experiment level. The fixture enables sharing only for its newly generated synthetic instance. MCP, assistant, training and instrument settings are not enabled by this adapter.
- Responses use explicit projections. No generic command endpoint, arbitrary paths, raw internal results, provider credentials, imports, writes, training or instrument operations are exposed. Requests with write methods, bodies or unexpected query fields are rejected. Unknown and unauthorized resources both return 404; invalid credentials return 401.
- Report reads verify the independent manifest pin, preserved source and normalized bytes, and Genesis history with the existing MS services. Reports retain origin declarations and `UNKNOWN` evidence, including approved workflow reviews. `SIMULATED` observations remain distinct. Approval does not establish instrument provenance or measurement accuracy.
- `X-Content-SHA256` hashes the exact response bytes, serialized with the existing deterministic JSON encoder. Reports contain the source, normalized-file and manifest SHA-256 values. These are integrity checks, not publisher signatures or scientific validation.
- A separate private audit file records actor, diagnostic surface, scope, allowlisted operation, request ID, outcome and report classification. It contains no bearer tokens, spectra or local artifact paths. Reads fail closed if audit recording fails. Research events are not appended for HTTP reads.
- At most eight owner operations are pending, with a 15-second HTTP wait deadline, bounded query values, maximum 1 MiB responses and no shared response caching. The CLI binds loopback only, uses one worker, disables access logs and proxy-header trust, and does not enable CORS.

The HTTP API is read-only. Normal engine startup can perform its existing recovery writes; the service audit writes separately. This is not an engine opened with SQLite read-only mode, a distributed transaction, or a multi-writer deployment. Job polling is intentionally absent because the current engine `job()` method can accept and publish finished worker results.

## Version 1 HTTP routes

Every route requires `Authorization: Bearer <service token>`. Tokens in URLs or cookies are not accepted. `X-VirtualLab-Surface: web|chatgpt|desktop` is an optional diagnostic label only. Instance IDs come from the server's configured instance; project/experiment/observation identifiers are rechecked before use.

Let `P` be `/v1/instances/{instance_id}/projects/{project_id}`, `E` be `P/experiments/{experiment_id}`, and `O` be `E/observations/{observation_id}`.

| GET route | Permission | Query / result |
| --- | --- | --- |
| `/v1/projects` | metadata | Only authorized, shared project metadata; server-selected instance/tenant IDs |
| `P/experiments` | metadata | `offset=0`, `limit=100` (1–100); experiment metadata page |
| `E` | metadata | Explicit reference and experiment metadata |
| `E/observations` | metadata | `offset=0`, `limit=100` (1–100); observation IDs, kind, evidence and digests |
| `O/report` | reports | Verified MS report projection, exact-byte checksum header |
| `O/spectrum` | spectrum | `offset=0`, `limit=100` (1–500); exact decimal centroid strings |
| `P/changes` | changes | `sequence=0`, `limit=100` (1–100); committed project events, bound cursor and `has_more` |

Change cursors bind instance and project in the route plus the returned cursor object. To resume, use that same route with its last sequence. Other project/instance cursor fields in the query are rejected. Experiment export restrictions filter experiment IDs from listings and change payloads. Polling is restartable; WebSocket/SSE updates, mutations, optimistic revisions and conflict resolution are not implemented here.

Project discovery has a 1 MiB response ceiling; large installations need discovery pagination and indexed membership queries before release. Current scoped readers reuse local engine APIs, which can scan history. The HTTP deadline bounds the waiting request, not execution time of an already running Python read. Timed-out reads retain their queue slot until completion. A durable host still needs resource supervision, ingress rate limits and quotas.

The frozen schemas are [shared report](../integrations/shared-engine-contract/service-ms-report.schema.json) and [operator access policy](../integrations/shared-engine-contract/service-access-policy.schema.json). The policy is not an HTTP request body and must never be writable by a website user. Update it by atomic file replacement under the service operator's OS access controls. A future account/membership resolver can replace this repository while preserving the authorization boundary; current grants are not automatically synchronized with GIC subscriptions.

## Reproduce qualification

From a reviewed source checkout or unpacked source package, create a Python 3.12 environment and install:

```bash
uv sync --locked --extra research-service --extra mcp --group service-test --group security
uv run --no-sync python -m scripts.verify_source_secrets
uv run --no-sync python -m scripts.export_research_service_contract --check
uv run --no-sync python -m pytest tests/application tests/integrations tests/research_service -q
uv run --no-sync python -m scripts.verify_research_service --output /new/empty/qualification-directory
```

The locked environment includes PyNaCl and all service/test dependencies. For an installation using pip instead of the lockfile:

```bash
python3.12 -m venv .venv-service
.venv-service/bin/python -m pip install '.[research-service]' 'pytest>=8' 'httpx>=0.28,<1'
.venv-service/bin/python -m scripts.export_research_service_contract --check
.venv-service/bin/python -m pytest tests/application tests/research_service -q
.venv-service/bin/python -m scripts.verify_research_service --output /new/empty/qualification-directory
```

The last command creates two synthetic tenants, a 128-centroid workflow per project, one real numerical run, fresh ephemeral signing credentials, and a separate loopback server process. It checks parity of independently issued tokens, project/experiment/report scope, report digests, cursor resumption, anonymous and cross-tenant denial, write rejection, revocation and unchanged research files. Only the public verification key is written; private keys and bearer tokens remain in memory. The process is stopped when the check finishes.

Evidence is `validation.json`, `verified-report.json`, `http-server.log` and `fixture/service-audit.jsonl` in that directory. Runtime fixture files and recordings stay outside the source package. Tested service versions are captured in `validation.json`; `uv.lock` now includes the service, MCP and review-tool groups. CI reproduces the headless tests, secret gate and separate-process HTTP qualification and uploads the selected synthetic evidence files. Secret scanning runs offline with reviewed exact non-secret digests; the existing Mol* vendor asset is hash-pinned and requires re-review if changed.

A sanitized [local validation summary](evidence/research-service-local-validation.json) is included in the review source so reviewers can inspect the reported counts and dependency versions without needing a separately linked output directory. It records local synthetic qualification, not live-account or scientific acceptance.

To start an operator-configured instance locally:

```bash
python -m virtual_lab.integrations.research_service.server \
  --root /explicit/hosted-instance \
  --policy /operator/service-access.json \
  --identity /operator/identity.json \
  --audit /operator/service-audit.jsonl
```

The identity file contains exactly `issuer`, `audience` and `public_keys` (key ID to RSA PEM public key). Use an identity broker specifically issuing service-audience tokens. This adapter is not a login server, OIDC discovery implementation, JWKS refresh service, Supabase session verifier or ChatGPT OAuth server. Verification-key rotation requires a controlled service restart. Do not place production issuer private keys in this service.

## Review package and remaining gates

`python -m scripts.prepare_research_source --output /new/virtual-lab-review-source.zip` packages the complete selected working source, tests, documentation and integration contracts with per-file hashes. `SOURCE-REVIEW.json` records the base commit, branch and whether uncommitted work is included. The source manifest and ZIP checksum pin the actual working files; the base commit alone does not represent this implementation. Local environments, runtime research data, Git internals and output directories are excluded. Existing synthetic/protocol test fixtures are included. This is a source snapshot, not a signed installer or public release. The existing release manifest describes an earlier MS milestone.

Completed locally:

- [x] Reviewable source preparation with source and transport schemas.
- [x] One owner-thread read service with verified identity and server grants.
- [x] Isolated synthetic workflow/report and numerical fixture, without BSA/customer data.
- [x] Independent HTTP client parity, cross-tenant denial, immediate revocation and file-integrity checks.
- [x] Negative tests for credentials, scope, settings restrictions, artifacts, audit availability and request bounds.

Still required before live shared-account access:

- [ ] Review and publish/push the selected source revision; review archive hashes if using the source package.
- [ ] Choose durable hosting/data location and configure private ingress, TLS, backups, supervision, rate limits and monitoring.
- [ ] Implement the existing GIC sign-in token broker, authoritative membership/entitlement resolver and a feature-gated server-side website reader; preserve existing paid access.
- [ ] Exercise actual GIC accounts, cross-account denial and revocation through the website.
- [ ] Implement separate authenticated MCP/OAuth and actual ChatGPT acceptance using the same service policy.
- [ ] Implement explicit, expiring, revocable desktop pairing; keep local data independent until a deliberate transfer is authorized.
- [ ] Add mutation consistency, idempotency/revisions, conflict handling, full application parity and operational qualification before expanding beyond read-only access.

No production website merge/deployment, public research endpoint, account migration, automatic upload or directory publication is performed by these scripts.
