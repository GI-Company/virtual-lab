# Shared research engine — desktop, hosted web and ChatGPT

The owner selected both a full interactive ChatGPT workspace and a paired desktop application, sharing projects and the research engine. The developing web adaptation at `https://globalintentcompany.space/virtual-lab/demo` also serves people who have not installed the beta. It should become another client of the shared services.

The public website and demo entry were inspected in the browser. The entry currently describes an online adaptation and presents a Paid/Enhanced access gate. The workflows behind that gate were not exercised. The owner says the web version is less advanced and under active development. No website changes, deployments, account actions or entitlement changes were performed here.

## Implemented foundation

`virtual_lab/application/` now owns the Qt-independent study, selection, numerical execution, simulation-result, output and run-storage implementations. The old `virtual_lab.gui.services.*` import paths re-export those same implementations for compatibility. The desktop controller uses the shared numerical persistence function; there is no separate copy of the scientific equations for the web client.

`ResearchEngine` owns one local instance identity, writer lease, query store, Genesis ledger, artifact root and resource slot. `HeadlessWorkspace` provides research context without Qt. `ResearchClient` provides the same versioned in-process command/response envelope to desktop-, web- and ChatGPT-labeled development adapters.

**This is not a hosted API, authentication system, completed web integration or completed ChatGPT plugin.** Client labels are diagnostic metadata, not authenticated identities or permissions. All current commands assume a trusted local instance owner. The production transport must authenticate the account, authorize tenant/project membership and apply data-sharing and operation permissions before dispatching any command. The local engine is not to be exposed directly to the internet.

## Working operations

| Area | Implemented operation |
| --- | --- |
| Instance | Stable UUID, owner-thread checks and one OS-owned writer lease |
| Projects | Create and list real projects through the existing study service |
| Experiments | Create/list/read with explicit instance, project and experiment IDs |
| Notebook | Save plans and conclusions with the existing content/evidence checks |
| Observations | Scoped metadata and integrity-checked saved result retrieval |
| Numerical work | Real subprocess simulations, persisted results and numerical certificates |
| Jobs | Idempotent submission, polling, cancellation, deadlines, output bounds and restart interruption |
| Comparison | Existing compatible saved-run comparison implementation |
| MS intake | Bounded CSV bytes, preserved original data, normalized points and existing metadata/consent validation |
| Change feed | Project-scoped committed-operation records with restartable instance/project cursors |

The MS binding preserves the strict existing pilot CSV contract and its dataset limits. It is not a new unrestricted laboratory ingestion service. Research results retain MODEL_ASSUMPTION, INFERRED, UNKNOWN and SIMULATED classifications as appropriate.

## Example: two clients, one engine

```python
from virtual_lab.application.engine import ResearchEngine
from virtual_lab.application.client import ResearchClient

engine = ResearchEngine('/new/isolated/research-instance')
desktop = ResearchClient(engine, surface='desktop')
web = ResearchClient(engine, surface='web')

project = desktop.request({
    'instance_id': engine.instance_id,
    'operation': 'project.create',
    'payload': {'name': 'Shared study', 'domain_id': 'physics_simulation'},
})['data']

experiment = web.request({
    'instance_id': engine.instance_id,
    'operation': 'experiment.create',
    'payload': {
        'project_id': project['id'],
        'name': 'Planned experiment',
        'question': 'What does the supported model predict?',
    },
})['data']

# Both adapters query the same persisted records; no directory replication occurs.
assert desktop.request({
    'instance_id': engine.instance_id,
    'operation': 'experiment.get',
    'reference': experiment,
})['data']['id'] == experiment['experiment_id']
engine.close()
```

The application command schema is exported alongside the reference, cursor and job schemas under `integrations/shared-engine-contract/`. These are internal service contracts; no HTTP URL or network authorization is implied.

## Ownership and jobs

The engine checks that every experiment reference belongs to its selected instance and project. Job/result lookups are bound to that experiment. Project cursors cannot be reused for another project or instance. A client changing its active view does not retarget a previously submitted job.

SQLite connections remain on the engine's owner thread. A transport must dispatch work to that owner, rather than call the engine from arbitrary HTTP worker threads. Expensive numerical work runs in a separate process with no Python socket connections or binds; the worker has no database or credential access. The owner alone accepts and registers the result.

The same resource slot coordinates managed inference, INTENT updates and shared numerical jobs within this engine. Numerical jobs have a deadline and output-size bound. Output model/configuration and SIMULATED state are checked before publication. Cancellation before acceptance discards the result. Duplicate numerical request IDs return the same job; reusing an ID with different inputs is rejected. This idempotency contract currently applies to numerical jobs, not every project/notebook mutation.

Job records survive restart. Interrupted owner-process jobs are marked INTERRUPTED and their unaccepted output is not promoted into observations. Recovery never kills a process solely from an old stored PID. Graceful shutdown cancels and joins the actual owned workers before releasing the research store.

Artifacts are bound to the selected instance root, not changed by unrelated process environment changes after service construction. Existing content-addressed records and hash verification remain in use.

## Change delivery

The engine appends `APPLICATION_CHANGE_COMMITTED` records with project/experiment and affected entity identifiers after successful operations. The cursor contains the instance ID, project ID and committed ledger sequence. Clients can request bounded pages and resume after restart. Raw unrelated ledger payloads are not returned by this feed.

The feed supports in-process polling and the separately qualified read-only HTTP adapter described below; WebSocket/SSE updates are not implemented. Existing desktop code still uses its normal local workspace and compatibility imports. A real paired desktop must use the owning service API instead of opening the server's database files. Two independent processes must not write the same SQLite directory.

File publication, observation insertion and ledger changes retain the existing service contracts; this phase does not claim a distributed atomic transaction across all stores. Multi-user transport, transactional outbox/revisions and conflict handling remain required before shared hosted use.

## Website integration direction

The production-linked `GI-Company/GiC` repository contains the [shared-engine integration blueprint in draft PR #15](https://github.com/GI-Company/GiC/pull/15). Reuse its browser client and existing account/plan flows. Do not replace its login or paid-access policy with client-supplied flags.

A production server boundary should:

1. Verify the website/ChatGPT user and resolve authorized organization, instance and projects server-side.
2. Enforce account entitlements, project roles, sharing categories and operation scopes before dispatch.
3. Translate authenticated HTTP/MCP requests into the same research service contract.
4. Return owned artifact handles/downloads and result projections, not arbitrary server filesystem paths or credentials.
5. Publish committed change events and support replay/conflicts across web, ChatGPT and desktop clients.
6. Route supported local hardware/models through explicit companion pairing; report disconnected/unavailable capabilities truthfully.

The next local milestone adds an [authenticated read-only HTTP adapter and synthetic qualification](read-only-research-service.md). Its operator grants and ephemeral test issuer are not connected to GIC accounts. OAuth integration, desktop pairing, live website persistence connection and full plugin UI remain unimplemented. The remaining biology/calibration/computational/INTENT/instrument interfaces still need their full service and UI bindings; the target remains the entire application.

## Verification

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/application -q
QT_QPA_PLATFORM=offscreen python -m pytest tests/models tests/projects tests/gui/test_cockpit_integration.py -q
QT_QPA_PLATFORM=cocoa python scripts/stress_navigation.py --cycles 5 --output /new/native-stress-directory
```

Tests use isolated local workspaces. They verify shared persisted records, real worker runs and numerical checks, idempotency, cancellation, scoped lookups, interleaved client contexts, changed-output rejection, job deadlines, owner crash/restart, instance-root isolation and headless imports with Qt/GUI/AI SDK imports blocked. They do not establish hosted authentication, real-time network transport, live laboratory acceptance or public plugin readiness.
