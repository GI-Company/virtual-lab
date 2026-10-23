# Notebook adapter follow-up verification

October 23, 2026. Shared base: `07f01f75f488fb40bfeab3962d5cbeae736ea414`. This follow-up extends the four isolated beta editions; main remains unchanged.

## Delivered behavior

Projects → **Model & instrument files** can execute a declared linear JSON predictor or import a declared instrument CSV, then attach the actual result to the active experiment. The result is inspectable, selectable as evidence for a human-authored conclusion, exportable as CSV, and retained inside a portable study package. It requires no AI service, instrument connection or network request.

Predictions remain PREDICTED. Operator-supplied predictor inputs and imported CSV samples are UNKNOWN, not authenticated measurements. Source manifests, original CSV bytes, inputs, outputs, source hashes and the original adapter fingerprint are retained. The recording timestamp means local attachment time, not physical acquisition time.

Inspection and import validate the artifact hash, record identity, experiment association, status and source-to-output consistency. Linear output accumulation is explicitly versioned and deterministic across BLAS summation orders. Later installed code does not overwrite the original recorded adapter fingerprint. These checks establish internal consistency of a declared mapping, not scientific correctness or trusted authorship.

CSV exports include units, status and source/artifact hashes. Formula-like source text is escaped for spreadsheet use; numeric results and archived source bytes are unchanged. Existing export destinations are preserved.

The header now checks all active study artifacts before claiming that study records are verified, including extension, plan and conclusion records when simulation runs also exist. It recognizes a verified ledger before any research result is saved and displays an integrity error when an active artifact fails verification.

## Actual local verification

| Check | Result |
|---|---|
| Complete pytest suite without optional AI SDK | **430 passed, 13 skipped**, 19.02 s |
| Complete pytest suite with optional Google SDK path | **454 passed, 10 skipped, 2 warnings**, 20.77 s |
| New regression cases | 14 cases covering source/citation round trips, semantic tampering after rehashing, status promotion, malformed data, GUI controls, CSV units/status/overwrite preservation, database failure, forged package rollback, spreadsheet formula text, retained adapter fingerprints, header integrity and deterministic arithmetic |
| Historical exports | Six historical study packages imported successfully into temporary workspaces |
| Existing research | 67 sampled research files remained byte-for-byte unchanged |
| Layout | Existing complete GUI layout scenario passed, including the new nested notebook tab; an 800×600 offscreen preview was also inspected |
| Packaging | Wheel built; both new GUI and record-validation modules included |
| Diff and credentials | Whitespace check clean; scoped changes reviewed; heuristic credential scan found no matching credentials |

The full suite also exercises the existing complete manual researcher and three student workflows. New extension round trips use the actual study service, with separate Qt GUI-control regression coverage. The local environment and skip categories are the same as the [initial security beta verification](security-beta.md); no live cloud or physical hardware validation is claimed. These local tests ran on macOS/Python 3.14, not the hosted Python 3.10–3.12 matrix.

## Failure and release boundaries

Artifact recording and database attachment span separate stores. A failed database attachment retains its immutable artifact and truthful `EXTENSION_ARTIFACT_RECORDED` event, but emits no successful attachment notification. Automated crash reconciliation remains operational work; no historical event is deleted or rewritten to conceal a failure.

Generic AI endpoint notebook integration, authenticated physical acquisition, device-specific calibration/sample validation, broader model formats and vendor adapters remain pending. CLI-created extension artifacts are not automatically attached to a study. Signed/authenticated authorship and scientific validation are separate from unsigned study-package consistency.

Raw output and JUnit XML are retained locally as `notebook-core.raw.log`, `notebook-sdk.raw.log`, `notebook-core-junit.xml`, and `notebook-sdk-junit.xml` under `hardening-release/security-beta-evidence`, alongside compatibility, packaging and research-preservation evidence. Hosted CI must pass independently; it was previously prevented from starting by a GitHub account billing lock.
