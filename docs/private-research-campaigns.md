# Private research campaigns

VirtualLab can now execute a user's finite, custom numerical study in its private
research service after the initiating HTTP client disconnects. This calls the
existing `ResearchEngine` and registered CPU models. The service owns the engine
on one thread and periodically advances persisted campaign checkpoints.

This is an opt-in local integration milestone, not a production launch. GIC login,
the website's research UI, ChatGPT private-project OAuth/MCP, and desktop pairing
are not connected to these routes yet. The public Free plugin is unchanged.

## What is implemented

- Custom objective, complete model configurations, plan SHA-256 and finite budgets.
- Authenticated creation, discovery, inspection, explicit start/resume, pause,
  cancellation, and numerical result retrieval within an existing experiment.
- Background execution without HTTP polling. One numerical child at a time,
  up to 16 active/paused/cancelling service campaigns, 1,000 campaigns per project.
- Live operator grants, project/experiment settings and original credential expiry
  checked on every scheduled tick. Revocation, policy errors and audit failures
  stop work and require review. No stored bearer token or private signing key.
- Idempotent creation and control commands, including delayed retries after pause.
  Lost job pointers are reconciled using the engine's persisted request IDs before
  cancellation, deadline handling or additional submission.
- Bounded result summaries with original artifact hashes, numerical checks,
  scientific limitations and `SIMULATED` classification. `X-Content-SHA256` hashes
  the exact response bytes. Saved result alteration fails artifact verification.
- Separate audit intents before mutation/result acceptance and scoped outcomes;
  research inputs and bearer credentials are excluded from that audit.

The results describe model assumptions and numerical calculations. They do not
establish biological validity, drug efficacy, experimental measurements, or a
training label. This milestone supports registered numerical configurations;
dataset upload, adaptive planning and wet-lab operations are separate workflows.

## Enable an isolated service

Install the locked headless environment from the repository:

```bash
uv sync --locked --extra research-service --extra mcp --group service-test --group security
```

Configure the existing [private service identity and policy](read-only-research-service.md)
for an explicitly selected instance. In each authorized grant, enable the needed
default-false flags: `campaign_read`, `campaign_write`, and `campaign_run`, alongside
`research_access`. The operator must also enable exports, cloud access and tools
in the instance's Settings and applicable administrator/project/experiment rules.
Enabling a route does not bypass these controls. Client `surface`, subscription
claims and project IDs never grant access.

```bash
python -m virtual_lab.integrations.research_service.server \
  --root /explicit/hosted-instance \
  --policy /operator/service-access.json \
  --identity /operator/identity.json \
  --audit /operator/service-audit.jsonl \
  --enable-campaigns
```

Without `--enable-campaigns`, the previous read-only behavior remains the default.
The listener still binds only loopback with one worker and no CORS. A production
host needs supervised execution, durable storage, TLS/private ingress, backups,
rate limits, monitoring and operational qualification. Do not run multiple
processes on the engine SQLite files, discover desktop workspaces automatically,
or upload local data implicitly.

## HTTP contract

Let `C` be
`/v1/instances/{instance_id}/projects/{project_id}/experiments/{experiment_id}/campaigns`.
Every request uses the existing short-lived service-audience bearer token.

| Method / route | Body or query | Required campaign grants |
| --- | --- | --- |
| `POST C` | Create object below | read + write |
| `GET C` | `offset=0`, `limit=100` (1–100) | read |
| `GET C/{id}` | None | read |
| `POST C/{id}/start` | `request_id`, `approved_plan_sha256` | read + write + run |
| `POST C/{id}/pause` | `request_id` | read + write |
| `POST C/{id}/cancel` | `request_id` | read + write |
| `GET C/{id}/results` | None | read |

Creation and start additionally require tools and cloud Settings permission;
returned data requires exports and cloud permission. Revoked execution authority
triggers host cancellation independently of whether the user can still issue a
cancel request. The execution grant is distinct from write and read grants.

Example create body (generate a new UUID for each deliberate operation):

```json
{
  "request_id": "6846391e-26d4-4fa0-92e3-72564898f0ca",
  "objective": "Compare two assumed concentrations in the gene-expression model",
  "configs": [
    {"model_id": "gene_expression", "concentration_um": 2.5, "members": 3, "duration_h": 1},
    {"model_id": "gene_expression", "concentration_um": 8.25, "members": 3, "duration_h": 1}
  ],
  "max_runs": 2,
  "max_seconds": 60
}
```

Inspect the returned normalized plan, then start by acknowledging its exact
`plan_sha256` and supplying a new `request_id`. This digest acknowledgement is not
a digital signature, independent scientific review, or a substitute for identity.
The plan cannot be edited after creation; changed conditions require a new plan.

Clients must retain an operation's UUID when retrying it after a timeout. Reusing
it with different content or another command returns `409 CAMPAIGN_CONFLICT`.
A replay returns the current campaign without applying the command again. Thus a
delayed start retry cannot undo a later pause. An interrupted command whose durable
outcome is uncertain returns 409: inspect the campaign, then make a deliberate
new command. The host never silently retries uncertain numerical work. At most
100 non-cancellation command records are accepted per campaign; cancellation
remains possible when that limit is reached.

Successful responses are deterministic JSON with an exact-byte SHA-256 header and
`Cache-Control: no-store`. Lists contain compact summaries; item reads return the
complete normalized plan. Results include per-state treated/control p05, median
and p95 values, model/configuration, artifact digest, numerical check and limitations.
These distribution quantiles reflect configured model uncertainty, not clinical
confidence intervals. Hashes provide byte integrity, not publisher signatures.

Requests require JSON, strict types and known fields. Duplicate keys, nonfinite
values, compressed bodies and malformed UUIDs are rejected. The body is limited
to 65,536 streamed UTF-8 bytes with a five-second read deadline, before buffering
the entire input. Responses are capped at 1 MiB. Errors are 400 (malformed), 401
(credentials), 404 (missing or unauthorized scope), 408 (body deadline), 409
(conflict/limit), 413 (body size), or 503 (unavailable). The read-only default
continues to reject mutation methods with 405.

Request schemas are frozen in `integrations/shared-engine-contract/` as
`service-campaign-create.schema.json`, `service-campaign-start.schema.json`, and
`service-campaign-command.schema.json`.

## Lifetime and recovery limits

Execution authority is bound to the actor, tenant, token ID and **original token
expiry**, at most 15 minutes. A fresh token used for reading does not renew it.
Explicit resume of a paused campaign can acknowledge a fresh authority lease, but
never resets the original wall-clock budget. Expiration/revocation moves work to
`NEEDS_REVIEW`; inspect retained results and create a new plan to continue.
Longer offline delegation is not implemented by inventing nonexpiring tokens.

A paused campaign launches no new jobs; an already active job can finish while
the host checkpoints it. Completed reports and paused checkpoints survive a
process restart. Shutdown cancels active children; interrupted/cancelled jobs
require review after restart instead of being silently rerun. Progress between
completed steps can continue on restart while its saved authority remains valid.
A scheduler metadata fault reaps children, fails subsequent writes closed, and
requires operator repair/restart; item views expose `host_status` where readable.

Deadlines are checked on owner ticks. Worker timeouts and output bounds are
separate existing engine limits. This is not an OS memory/CPU quota, a financial
budget, multi-host scheduling, automatic backups or a crash-atomic distributed
transaction. SQLite checkpoints, artifact files, Genesis and service audit have
separate writes; uncertain outcomes are surfaced rather than claimed atomic.

## Reproduce validation

```bash
uv run --no-sync python -m scripts.export_research_service_contract --check
uv run --no-sync python -m scripts.verify_source_secrets
uv run --no-sync python -m pytest tests/application tests/integrations tests/research_service -q
uv run --no-sync python -m scripts.verify_research_service --output /new/read-only-evidence
uv run --no-sync python -m scripts.verify_campaign_service --output /new/campaign-evidence
```

The latter command creates an isolated synthetic instance, ephemeral credentials
and a separate loopback server. It closes the initiating client, waits for audited
background completion without HTTP polling, compares three independent clients'
result hashes, restarts the process, tests revocation and stops the server. It
never opens another process on the running engine database. `validation.json`,
`campaign-results.json` and its `.sha256` file are the shareable evidence.

HTTP clients stand in for future interfaces; they are not a live GIC/ChatGPT/native
account acceptance test. CI is configured to repeat headless service checks on
Linux, macOS and Windows. Local macOS results do not establish that those CI runs
have passed or that native installers are qualified.

## Remaining product task list

- [x] Custom bounded plans use the existing engine and persisted evidence.
- [x] Opt-in authenticated controls and background owner-thread execution.
- [x] Retry safety, revocation, original credential expiry and cleanup.
- [x] Restartable progress and checksum-bearing numerical result projections.
- [x] Synthetic HTTP qualification and cross-platform CI configuration.
- [ ] Independently review this source revision and run Linux/Windows CI.
- [ ] Deploy a supervised private engine with backup/restore and resource quotas.
- [ ] Connect GIC sign-in and authoritative account/project/entitlement resolution.
- [ ] Add the website project/campaign UI using these exact contracts.
- [ ] Add private ChatGPT OAuth/MCP controls and explicit desktop pairing.
- [ ] Demonstrate one real account's project/results across all three products,
      then revoke access and prove all three are denied.
- [ ] Add authorized dataset transfer and qualified MS analysis campaigns.
- [ ] Model renewable long-duration delegation, scheduling/events and financial budgets.
- [ ] Add an adaptive planner that proposes reviewed steps and never treats its
      predictions as experimental truth.
