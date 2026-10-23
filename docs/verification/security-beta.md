# Security beta verification, October 23, 2026

Subsequent desktop notebook integration and updated test results are recorded in the [notebook follow-up](notebook-beta.md). The results below describe the initial security beta batch.

This batch starts from `33e477afabd0b8de729c37f692d28a2c65ecc9ea`. It prepares four beta candidates without changing main or production research data. It is a scoped security/provenance hardening verification, not a replacement for the original 38-finding independent audit.

## Actual local results

| Check | Result |
|---|---|
| Full pytest suite without optional AI SDK | **416 passed, 13 skipped**, 20.32 s |
| Full pytest suite with optional Google SDK path | **440 passed, 10 skipped, 2 warnings**, 20.00 s |
| Researcher manual workflow | Passed: plan → two runs → compare → numerical check → CSV → cited conclusion → study export → restart → import |
| Student workflows | Same complete flow passed separately for high-school, undergraduate and graduate, with AI imports blocked |
| Packaged branch defaults | Each of the three student default manifests independently passed the complete workflow, without an edition environment override |
| Historical exports | **6/6 imported** into clean temporary workspaces; observation counts, hashes and original artifact bytes preserved |
| Existing research | **67/67 files unchanged** by before/after SHA-256; historical database inspection used temporary copies |
| Compatibility ledgers | Every ledger in the sampled historical inventory verified on copies; schema-1 upgrade tests preserve original event fields/hashes |
| Extension execution | Actual ODE/DOP853 check, linear predictor and CSV acquisition passed through public CLI in a scratch workspace |
| Generic AI adapter | Real local HTTP test server exercised explicit opt-in, request/response parsing, non-authoritative output and credential exclusion; no live cloud claim |
| Transport | Unpaired rejection, paired target routing, no broadcasting, protocol-typed camera request/result and actual ledger write passed with test clients |
| Packaging | Wheel built; edition JSON, extension modules and RFC canonicalization dependency present |
| Diff/credentials | `git diff --check` clean; scoped diff reviewed; heuristic credential scan found no matching credentials in tracked/non-ignored text files |

Local runtime: Python 3.14 on macOS; published CI targets remain Python 3.10–3.12 and require independent hosted verification. The passing local suite does not establish compatibility across those interpreters or operating systems. The wheel is a Python wheel, not a signed desktop installer.

## Findings and boundaries addressed

| Area | Concrete remediation | Evidence |
|---|---|---|
| C-4 exposed publisher | Removed fallback signing seed; revoked public key for both publisher/program roles; separately configured operator trust cannot restore it | `tests/core/test_security_beta.py` revoked-key, explicit-trust and no-implicit-key checks |
| C-7 durable replay | Disk ledger required; full signed envelope and exact decision signature; rule pass; timezone-aware window; claim before side effect, under SQLite write lock | Sequential audit test; concurrent two-connection execution test; restart after post-side-effect failure test |
| C-8 fabricated execution | Eleven retired tool bodies raise, legacy agent/workbench return failure, and alternate unsigned approval/action bypass raises | Source review; updated `tests/ai/test_agent_policy.py` verifies legacy calls neither execute nor append fake events |
| C-2 historical split ledgers | New writes use genesis; both histories verified read-only, identities namespaced, source shown in UI; no destructive merge | Collision/count/hash tests and provenance UI source-label test |
| Canonical JSON / M-5 | Actual RFC 8785 implementation for new writes, declared schemes for signed manifests, versioned legacy verification | IEEE-754/negative-zero/UTF-16 key-order vectors; duplicate/nonfinite/large-integer rejection |
| Historical ledger migration | Preflight before DDL; schema-1 encoder retained; append schema-2 without changing old rows | Tests for both historical negative-zero encodings, exact original fields and invalid DB byte preservation |
| H-11 remaining ensemble scope | Only declared controls sampled; internal rates derived afterward; reference solver receives same prepared member parameters | RHO four-control test and DOP853 checks; existing Spearman labels/zero-variance tests pass |
| Provenance timestamps | Full provenance hash includes timestamp; explicitly separate content fingerprint | Timestamp-tampering regression |
| Bundle consistency | SQLite backup captures committed WAL records; output and sidecars excluded; atomic destination staging | Live-WAL bundle test, repeated build test, existing acceptance/tampering tests |
| Imported model execution | No automatic installed Python entry-point execution; explicit opt-in for trusted Python programs; data-only ODE adapter has an allowlisted AST | Startup opt-in and unsafe-expression tests; closed-form imported decay test; existing importer traversal tests |
| Transport identity/control | Loopback receiver off until requested; pairing on every channel; bound IDs; target-specific commands; typed camera responses | Extension transport/control tests plus existing packet, stride and connection tests |
| Editions | Shared implementation, separate defaults/storage, initial guided student presentation | Edition default/storage tests and complete student workflow subprocesses |

A hash chain detects inconsistency relative to its current bytes; it is not an external signature or defense against a privileged local attacker. An unsigned `.vlab-study` preserves byte integrity, not publisher authenticity. Old bundles using the exposed key intentionally lose trusted status. No historical research record is silently re-signed, rehashed or upgraded into a stronger scientific claim.

## Skips and warnings

Both runs skipped four MLX/hardware modules because `VIRTUALLAB_RUN_MLX_TESTS` was not enabled, two live Gemini cases because live cloud tests were not enabled, one pandas case because pandas was absent, one AlphaGenome case because its package was absent, and two Kotlin interop cases because Gradle was absent. Without the optional AI SDK, three additional request-gate/ADK/Vertex modules skipped because the AI extra was absent. This accounts for 10 and 13 skips respectively; collection-level skips are included.

The SDK run reported Google's Python 3.17-targeted `_UnionGenericAlias` deprecation warning and an ADK experimental JSON-schema tool declaration warning. Neither is suppressed or counted as a passed feature.

## Release scope

Suitable candidate for supervised beta testing of the manual research workflow and the listed adapter examples. Not cleared for clinical use, arbitrary untrusted executable models, network-exposed equipment control or validation claims about physical samples.

General-release gates remain: physical instrumentation/client pairing validation, authenticated remote acquisition and replay handling, calibration/sample identity assurance, vendor/model format adapters, notebook integration for CLI extension results, live provider-specific testing, hosted cross-platform CI and operational signer/recovery review. See [beta testing](../beta-testing.md) and [adapter scope](../extensions.md).

Raw pytest outputs (including skip reasons), JUnit XML, compatibility inventory, before/after research hashes, CLI outputs, wheel build log and source/diff snapshots are retained in the local task's `hardening-release/security-beta-evidence` directory. No credentials are included in this report.
