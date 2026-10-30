# Mild Biotec initial MS workflow pilot

Status: internal engineering release candidate, `1.0.0b2+ms.1`. Laboratory acceptance, data permissions, deployment choice and commercial terms remain pending. This implements a local centroid peak-list workflow; it does not validate measurements, protein identity, purity, calibration or structure.

## Install and launch without AI credentials

Use Python 3.10, 3.11 or 3.12 and uv 0.13.6. From the repository:

```bash
python -m pip install uv==0.13.6
uv sync --locked --extra cockpit --extra pilot
uv run --no-sync virtuallab-ms-pilot
```

The dedicated pilot window uses the existing VirtualLab project, experiment, observation and ledger services. It does not load AI providers, start instrument listeners, discover instruments or make network requests. The full cockpit also has an **MS Workflow** tab; use the dedicated window for the offline pilot. Installers can require network access to download dependencies. Runtime data processing is local.

For a built wheel in an otherwise clean environment:

```bash
python -m pip install 'virtual_lab-1.0.0b2+ms.1-py3-none-any.whl[cockpit,pilot]'
virtuallab-ms-pilot
```

The wheel alone does not include third-party dependencies. `uv.lock` records version and artifact hashes, including Python-specific dependency resolutions. Export requirements with `uv export --locked --extra cockpit --extra pilot --no-emit-project --no-dev` for a hash-checked dependency installation or an approved offline wheelhouse.

## Researcher workflow

1. In **Projects**, create a project and an experiment with a workflow question.
2. Open **MS Workflow**. Select the permitted CSV and enter pilot, dataset, sample, instrument and operator/pseudonym identifiers. Acquisition time and units can remain unspecified.
3. Confirm that the data is synthetic or approved nonconfidential data permitted for the pilot.
4. Select **Validate and preview**. Inspect the spectrum and the original/normalized previews. Finalize import only after validation passes. Changes to the selected source or metadata require another preview.
5. Select the imported dataset. Verify integrity, compare repeat processing, and record an approval or rejection with a reviewer pseudonym and note.
6. Export a JSON or PDF workflow report. Use Projects to exchange a complete `.vlab-study` package containing the preserved original, normalized peaks and manifest. Imported packages can be viewed in the receiving workspace's MS panel.

Workflow approval never changes the evidence state from `UNKNOWN` to `MEASURED`. Identifiers and acquisition times are supplied assertions, not authenticated instrument metadata. The initial pilot is limited to three distinct dataset IDs per pilot ID; repeat imports retain separate run IDs and explicit duplicate references.

## Input contract

UTF-8 (optional BOM), exactly two CSV columns in this order:

```csv
mz,intensity
101.53,2400
102.53,925
101.53,12
```

- Maximum original file size: 16 MiB; maximum centroid entries: 100,000. Reads and manifest sizes are bounded. Memory use scales with these fixed limits; this is not a streaming/native-scan MS reader.
- Numeric fields use an explicit decimal grammar: no missing values, whitespace padding, formulas, NaN, infinity, underscores or extra fields. Blank rows are rejected.
- m/z must be positive and intensity nonnegative. Nonzero values have decimal order between -100 and 100 and at most 100 significant digits. These are implementation bounds, not scientific QC thresholds. Zero intensity is allowed.
- Identifiers use 1-80 ASCII letters/digits with dots, underscores or hyphens after the first character. Acquisition times, when provided, require ISO 8601 timezone information and are stored in UTC.
- Units are entered explicitly or stored as JSON `null`; no units are inferred. The m/z column name identifies its intended meaning, not its acquisition convention.
- Original bytes are retained as `source.csv`. `peaks.csv` uses exact decimal canonicalization, LF line endings and sorting by m/z then intensity. Duplicate entries remain. No filtering, centroiding, rescaling, deconvolution or recalibration occurs.
- Decimal text is preserved exactly in value, avoiding binary floating-point rounding during normalization. The graph uses floating-point coordinates for display only.

## Artifacts, provenance and review

Every run has a UUID directory containing `source.csv`, `peaks.csv` and a strict version-2 `manifest.json`. The manifest records pilot/dataset/sample/instrument/operator IDs, optional acquisition time and units, software and processing versions, source/normalized SHA-256 digests, warnings, explicit approval, duplicate references and `UNKNOWN` evidence.

Genesis events record registration, validation, normalization, completion, reruns, workflow review and exports. Rejected inputs record only an error code and experiment reference; they do not copy the source content or source filename into application logs. Structured Python logging uses event codes without sample content, identifiers or paths. The scientific audit ledger intentionally contains the supplied metadata and must be protected with the study data.

The queryable observation store links each run to its experiment. Its manifest digest is also pinned in the local Genesis Ledger. Local viewing, reruns and report exports verify both that pin and the artifact checksums. Standalone `verify` checks the supplied unsigned manifest and cannot authenticate it. A valid replacement manifest is detected only when checked against an independently retained digest, local record or trusted signature.

The ledger is a local append-only hash chain. Someone able to replace the entire local database and all artifacts can replace that history; it is not independent instrument attestation. `.vlab-study` packages are explicitly unsigned and offer byte integrity, not publisher identity. They carry source/normalized data and the manifest, but not the original ledger review history; include the separate workflow report or a signed `.vlab` export when exchanging that history.

For a signed `.vlab` export, `virtual_lab.pilots.bundles.export_signed_bundle(service, run_id, destination, signing_key)` uses the existing canonical manifest, Ed25519 signature, publisher-role trust check and `.vlab` verifier. The caller must supply a private key and configure an independent trust anchor through the existing signer registry. Public demonstration keys are refused. No key is generated, embedded, auto-trusted or uploaded by the pilot. Production signer storage/distribution is an outstanding deployment decision. The scoped export ledger references only the selected run's original events; unrelated study events are not exported. A signature attests the signing publisher's bytes, not instrument origin.

## Descriptive metrics and reports

The spectrum supports pan, zoom, cursor coordinates and optional log intensity display (zero points are omitted only from that display). Original/normalized previews show the first 16 KiB, clearly labeled; stored artifacts contain the full data.

Reports include identifiers, acquisition/processing information, validation status, warnings/errors, peak count, m/z range, base peak, exact summed centroid intensity, repeated m/z entry count, hashes, rerun result, review status, evidence history, software version and limitations. Summed centroid intensity is not labeled instrument-reported total ion current. Numeric summaries in JSON are decimal strings to preserve precision.

The same report snapshot produces identical JSON and PDF bytes. A later review, rerun or export adds lifecycle events and therefore produces a different report snapshot. Repeat-processing acceptance concerns normalized CSV bytes and digest. A report can reconstruct this implemented normalization method from the accompanying source and versioned processing contract; it does not reconstruct upstream instrument processing.

## Storage, retention and recovery

Pilot files are stored under `ms-pilot-runs` in the existing VirtualLab application data directory:

- macOS: `~/Library/Application Support/VirtualLab/cockpit`
- Windows: `%LOCALAPPDATA%/VirtualLab/cockpit`
- Linux: `$XDG_DATA_HOME/VirtualLab/cockpit` or `~/.local/share/VirtualLab/cockpit`

Set `VIRTUALLAB_DATA_DIR` to a dedicated pilot directory **before launch** to isolate retention, access and deletion. Use a canonical local path with no symbolic links in any path component. Input, output and artifact symlinks are rejected. On POSIX systems new pilot run directories are private and artifact files are mode 0600. On Windows use an account-restricted folder and OS access controls. There is no application encryption, role management, automatic retention expiry, backup erasure or secure-delete guarantee.

Only one application instance should write a pilot directory at a time. Files are staged privately, flushed and published before completion. Failed writes remove their staged files. A restart marks registered imports without a completion event as failed, renames their manifests to `manifest.interrupted.json`, and removes any incomplete query-store observations. Complete runs alone appear in the local dataset list. Hidden `.ms-intake-*` remnants from a killed process are not automatically deleted because they may belong to a running process. Close all instances before inspecting or deleting remnants.

Agree a retention period before data exchange. After closing VirtualLab, delete the dedicated pilot directory and separately delete exported packages/reports, staging remnants and backups according to the agreed policy. Do not remove a shared application directory containing unrelated studies. This is ordinary file deletion; it does not guarantee forensic erasure. The software sends no telemetry or automatic uploads. Export/transfer authorization and the chosen sharing channel remain the parties' responsibility.

## Verification and synthetic demo

```bash
uv sync --locked --extra cockpit --extra pilot --extra dev
uv run --no-sync python -m pytest -q
uv run --no-sync python scripts/ms_pilot_demo.py --output /absolute/new/demo-directory
```

The demo uses only the committed synthetic fixture, creates a project/experiment, imports, verifies, reruns, reviews and exports JSON/PDF and a complete study package. It also captures the real desktop panel. `tests/fixtures/ms-pilot` is synthetic; no partner dataset belongs in Git. Generated outputs, local data and temporary files are ignored.

Tests cover exact normalization and precision, invalid schemas/numbers/encoding, size/row limits, duplicate imports/centroids, permission gating, path/symlink attacks, manifest type/metadata/key manipulation, artifact changes, replacement relative to an external digest, signed-bundle tampering/replacement, lifecycle traceability, failed writes, restart recovery, review semantics, deterministic JSON/PDF, study exchange and offline GUI operation. Live cloud and hardware tests require separate opt-in and are excluded from offline acceptance.

CI uses locked dependencies on Python 3.10/3.11/3.12, a separate optional-AI compatibility job, Windows/macOS pilot smoke jobs and two-build wheel/source comparisons with wheel RECORD verification. Existing hosted jobs were prevented from starting by a GitHub account billing lock (confirmed from run 40994044526); a maintainer must resolve the account issue before hosted CI can substantiate these checks. Repository branch rules must require the chosen matrix and smoke checks after that issue is resolved. Local macOS results do not certify Windows or Linux behavior.

## Local verification record

Verified on macOS with locked installations: Python 3.10, 3.11 and 3.12 each passed **439 tests**, with 13 explicitly skipped optional/live/hardware cases. A separate Python 3.12 environment with optional AI dependencies passed **463 tests**, with 10 skips. Live service calls and laboratory scientific acceptance were not performed. The generated JUnit records and local validation summary are retained with the build outputs.

Two builds produced identical wheel and source-archive bytes; wheel RECORD entries were checked. A clean, non-editable wheel installation completed synthetic import, rerun, JSON/PDF export and GUI construction with no AI packages and with socket connections/binds blocked. The demo desktop screenshot and both report pages were visually inspected. These checks establish local workflow behavior, not cross-platform or scientific acceptance.

## Release and external gates

The pilot release candidate is versioned independently and should be reviewed as ingestion, provenance, reporting, GUI and release increments. No code merge or partner acceptance is implied by a local tag or draft PR.

Before external execution, confirm with Mild Biotec: first workflow and export format; the authorized datasets (up to three); metadata and report expectations; reviewer; OS and security preferences; acceptance criteria; permitted uses, retention and sharing; IP/confidentiality/licensing and commercial terms. The public repository's licensing decision remains with its owner; this change does not add a license or change ownership.

Native vendor exports/mzML, multiple scans/chromatograms, advanced analysis, scientific performance benchmarks, proprietary/regulated data, remote access and live instrument control remain outside this initial pilot. The indicative pilot schedule starts only after the parties agree scope, permissions and test materials.
