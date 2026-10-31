# VirtualLab Research architecture and INTENT task list

Scope decision: implement in reviewable milestones. Complete BSA verification/import and the guarded experiment controller first, while preserving the offline MS pilot. Later phases below remain explicit work rather than implied functionality. No multi-user or scientific-performance claim is created by this checklist.

## Milestone 1: BSA evidence and prototype audit (completed locally)

- [x] Inspect the supplied archive before executing its code; retain supplied files unchanged outside Git.
- [x] Independently verify indexed mzML index pointer and checksum against the HUPO-PSI definition.
- [x] Reconstruct the original wrapper and match its recorded SHA-256.
- [x] Compare all 1,684 spectra / 479,455 measurement pairs with the upstream OpenMS example.
- [x] Run the five supplied verification tests in an isolated working copy.
- [x] Rerun the sequential replay and reproduce the approximate pre-update MAE and historical-mean baseline.
- [x] Import the three extracted CSVs into one VirtualLab experiment; verify preservation, normalization, reruns, alterations, review and hashed reports.
- [x] Record all three as scans of the same acquisition; preserve UNKNOWN provenance.
- [x] Reject the scan-summary table from the strict spectrum importer; do not infer protein identity or structure.
- [x] Record prototype/checkpoint limitations, environment and source references in local evidence.

## Milestone 2: Controlled INTENT experiment model (completed locally; experimental)

- [x] Version feature encoding, target definition, units and normalization explicitly.
- [x] Keep the existing assistant switch separate from the new default-off INTENT prediction and learning controls (central settings/provider policy remains milestone 4).
- [x] Enforce switches and project training permission at the service layer.
- [x] Commit predictions to Genesis before eligible outcomes; bind checkpoint and feature hashes.
- [x] Accept only separately recorded measurement artifacts; reject predicted, simulated, unknown or incomplete research outcomes for genuine training.
- [x] Require a trusted, signed review scoped to the observation, target, project, experiment and intended use; reject demonstration signing keys.
- [x] Prevent duplicate training and repeated use of scans from the same claimed independent acquisition group.
- [x] Separate model candidates from the active prediction checkpoint; no automatic promotion based on training loss.
- [x] Bound replay memory and preserve weights, configuration, random state, optimizer identity and lineage in immutable hashed checkpoints.
- [x] Retain candidate-evaluation, rejection, promotion and rollback events in Genesis.
- [x] Require independent frozen holdout evidence and baseline comparisons for promotion.
- [x] Test disabled modes, forgery, tampering, chronology, idempotency, interruption, restart and project isolation.
- [x] Add an experimental local INTENT panel with real status, checkpoint history and explicit limitations.
- [x] Keep training outside the Qt process and preserve working research when AI/learning are disabled.

## Milestone 3: Discipline navigation and project persistence (completed locally)

- [x] Shared domain registry with enabled, experimental and unavailable tools.
- [x] Home -> discipline project library -> dedicated workstation using the existing study/evidence services.
- [x] Safe project domain migration preserving project IDs, experiment links and evidence.
- [x] Search, recent projects, breadcrumbs and restored active experiment/dataset/tool state.
- [x] Dedicated MS workstation first; expose other installed capabilities without fabricated availability.
- [x] Test project switching, reopen/restart and absence of cross-project observations.
- [x] Keep Research and Academia presentation profiles on common core packages.

## Milestone 4: Central settings and inference providers (next)

- [ ] Versioned settings repository and migrations, independent of scattered environment changes.
- [ ] Central General, AI & Models, INTENT, Monitor, Privacy and Performance pages.
- [ ] Provider interface, model registry, capability discovery, connection tests, activation, cancellation and cleanup.
- [ ] Adapt existing Gemini/Vertex and embedded MLX integrations; add compatible-server adapters as separately verified capabilities.
- [ ] Keep credentials in the OS store; never in JSON, logs or exported settings.
- [ ] Treat loopback, LAN and cloud routes distinctly; never fall back from local to cloud silently.
- [ ] Restrictive policy hierarchy: administrator -> application -> project -> experiment.
- [ ] Apply policy before model calls, tool execution, training and governed exports.
- [ ] Coordinate resource limits across inference/training; test cancellation and offline operation.

## Milestone 5: Learning monitor and prospective validation (later)

- [ ] Display logged pre-update errors, training loss, baseline comparisons, coverage, rejection reasons and resource use.
- [ ] Frozen independent holdout datasets split by acquisition/study/sample batch, not arbitrary scans.
- [ ] Validated uncertainty/calibration only when supported by independent evidence.
- [ ] Drift/forgetting checks and reversible manual model promotion with checkpoint lineage.
- [ ] Agree one scientifically meaningful target with laboratory reviewers before real research training.
- [ ] Obtain explicit data-use/training permissions; the BSA retrospective replay is not lab acceptance or generalization evidence.

## Milestone 6: Shared instances and commercial release (later / external)

- [ ] Authenticated shared server with permissions and server-owned transactional writes.
- [ ] Committed-change events, cursors/replay, revisions and reconnect/conflict handling.
- [ ] Explicit instance switching and selective sharing; no automatic cross-instance replication.
- [ ] Decide deployment/data location, production trust anchors, licensing and commercial terms.
- [ ] Resolve hosted CI account billing and obtain target-OS and laboratory acceptance.

## Local validation and remaining release gates

See [controller and evidence notes](../intent-experiment-controller.md) for signed-review contracts, the institutional trust-anchor prerequisite, software-only test scope and reproducible commands. The supplied BSA data never become verified training outcomes. Source datasets, trained checkpoint files, recordings and evidence packets stay outside Git. Milestone 3 adds [local discipline navigation and project persistence](../research-discipline-navigation.md). Central settings, institutional reviewer enrollment and distributed collaboration remain outstanding. The existing MS release manifest describes the earlier MS release; this branch is a separate experimental source milestone, not a new certified release.

## Completion rules

Check an item only after code or evidence is verified. Distinguish current software tests from proposed functionality, engineering demos from research training, and local approvals from authenticated multi-user authorization. Do not promote model predictions to experimental observations. Do not rewrite or train on supplied data merely because a file appears.
