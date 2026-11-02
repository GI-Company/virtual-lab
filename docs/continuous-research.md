# Continuous research — implementation and task list

The product objective is project-based research using a researcher's own conditions and supported datasets across desktop, web and ChatGPT. The three-preset public demonstration is an introduction, not the online research product.

## Completed local foundation

- [x] `ResearchCampaigns` wraps the actual shared `ResearchEngine`; it does not duplicate the scientific solver.
- [x] Persist a custom objective, full validated CPU simulation configurations, plan digest, run-count limit and wall-clock limit in the engine-owned SQLite store.
- [x] Start only when a trusted local caller acknowledges the exact saved plan digest. This acknowledgement is not identity verification, a digital signature, or independent human approval.
- [x] Execute one planned job at a time through existing engine workers. Stable per-step request IDs prevent duplicate job submission after a lost checkpoint.
- [x] Preserve result observation IDs and campaign events in the existing project/change-feed context. Observations remain SIMULATED. No generated result is treated as a laboratory measurement or training label.
- [x] Pause new work, resume between completed steps after closing/reopening the engine, cancel active work, and stop on exhausted budgets or interrupted/failed jobs.
- [x] Require review instead of silently retrying a cancelled/interrupted scientific job. Completed results remain available.
- [x] Exercise custom conditions that are not the public presets, actual numerical workers, restart recovery, scoped access, idempotency, cancellation, plan alteration and limits.

The controller is a trusted local application API. Create it on the engine owner thread with `ResearchCampaigns(engine)`, call `create(reference, objective=..., configs=[...], max_runs=..., max_seconds=...)`, inspect the returned plan, then `start(..., approved_plan_sha256=...)`. A host calls `advance(reference, campaign_id)` regularly; `get` inspects persisted progress. It never creates its own thread or opens a second process on the engine database. The [opt-in private campaign service](private-research-campaigns.md) now supplies authenticated controls, owner-thread ticks, expiring execution authority and numerical report projections. The default read-only service and public MCP remain unchanged in capability.

Pause stops further submissions; an already active job may finish and be checkpointed by subsequent ticks. Gracefully closing an engine cancels its active worker. On reopening, a campaign with an unfinished job requires review rather than claiming that the computation survived shutdown. Recovery between completed steps is supported.

The wall-clock deadline includes paused time and cannot be reset by resuming. It is checked on host ticks; it is not an operating-system CPU quota or a monetary budget. Engine worker timeouts remain separate. A stopped host cannot advance a campaign. Plan digests detect changes relative to the stored digest, not an attacker replacing both; ledger events record the original digest. Checkpoint and ledger writes use separate existing databases and are not one distributed transaction.

## Required before hosted continuous research

- [x] Local service owner-thread tick dispatch, persisted checkpoints, restart recovery and permission checks before each new job.
- [ ] Production hosting, durable storage, supervision, backups and operational recovery qualification.
- [ ] Authenticate GIC accounts and enforce tenant/project membership, supported operations and entitlements server-side. The local digest acknowledgement must never substitute for this authority.
- [x] Opt-in campaign create/read/start/pause/cancel transport with synthetic authorization, retry, expiry and revocation tests; read-only remains the default.
- [ ] Connect the same project and evidence to the web and ChatGPT through private-project OAuth/MCP. User-initiated uploads must preserve original bytes and explicit provenance.
- [ ] Support scheduled and event-driven continuation, delivery deduplication, polling cursors, revocation, notification preferences and missed-event recovery. A plugin tool response alone is not a background scheduler.
- [ ] Add independently configured inference access for an adaptive planner. Proposals outside the acknowledged plan require a new review; no self-generated observations become experimental truth.
- [ ] Add supported dataset-analysis workflows, starting with existing MS ingestion/integrity/reprocessing/comparison, then qualify each additional scientific adapter separately.
- [ ] Add enforceable compute/concurrency/financial budgets, elapsed usage accounting, cancellation monitoring and useful failure reports.
- [ ] Test an actual account across desktop/web/ChatGPT, host restart, denied unrelated account, revoked permissions and scheduled/event-triggered execution.

First live-account acceptance: a user defines custom conditions in one project, starts a bounded campaign, closes the browser, sees retained progress after host restart, and retrieves matching evidence through the website and ChatGPT. Then revoke access and verify no additional work or reads are permitted. Independent synthetic HTTP clients now demonstrate these service mechanics locally; actual GIC/ChatGPT/desktop integration remains outstanding.

Drug discovery capabilities require suitable models, data and validation. This foundation establishes reliable computational workflow execution; it does not establish drug efficacy prediction, autonomous wet-lab operation or an independently validated discovery engine.
