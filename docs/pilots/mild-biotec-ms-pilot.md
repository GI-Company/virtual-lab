# Mild Biotec MS workflow pilot — engineering readiness

**Status:** developer intake harness only; not a validated mass spectrometry analysis or clinical instrument system.

## Scope implemented in the starter

`virtual_lab.pilots.ms_workflow` imports a strictly defined two-column UTF-8 centroid CSV (`mz,intensity`) and produces a run directory with the original `source.csv`, a deterministically sorted `peaks.csv`, and a JSON manifest. The manifest records a source/normalized SHA-256 digest, UTC timestamps, operator/instrument/sample identifiers, peak count, and explicit epistemic limitations. Import is local and requires an explicit `--approved-nonconfidential` flag. `verify` compares files with the recorded hashes and checks deterministic normalization; it does **not** verify laboratory provenance or prevent an adversary from replacing both files and an unsigned manifest.

No source datasets are committed. Do not import confidential, human-subject, proprietary, controlled, or patient data until a written use agreement and adequate access controls are in place. This harness provides no encryption at rest, role-based access control, network transport, or signed chain of custody. Only use data your team has permission to process.

## Quick local test (synthetic or approved nonconfidential data)

Prepare `example.csv`:

```csv
mz,intensity
100.0,12
101.0,4
```

```bash
python -m virtual_lab.pilots.ms_workflow import example.csv \
  --output-root ./ms-pilot-runs \
  --sample-id synthetic-001 \
  --instrument-id instrument-unspecified \
  --operator-id test-operator \
  --approved-nonconfidential

python -m virtual_lab.pilots.ms_workflow verify ./ms-pilot-runs/<run-uuid>/manifest.json
python -m pytest -q tests/pilots/test_ms_workflow.py
```

The saved `epistemic_state` is `UNKNOWN` regardless of user-submitted metadata because source authenticity and instrument calibration are not independently verified. A centroid peak list is not by itself an unmodified physical measurement. Existing `virtual_lab.matter.virtual_mass_spec` predicts a limited formula-based isotope envelope and is **not** a protein/MS-MS identification engine.

## Planned next increments after instrument details are agreed

1. Instrument-export adapters (vendor CSV, mzML where suitable) and acquisition metadata mapping; no silent assumptions about labels, preprocessing, or units.
2. Multi-scan and replicate handling, QC dashboards, file-level provenance links to VirtualLab evidence and signed `.vlab` study bundles.
3. Defined quality metrics with versioned benchmark fixtures and independent instrument data for validation. Report accuracy, tolerances, and failure modes explicitly.
4. Protein or antibody analysis only after the partners select specific use cases and provide appropriately licensed reference data and accepted scientific methods. Current source code cannot infer HOS, binding, purity, or structural changes from centroid peaks alone.

## Feedback needed from Mild Biotec

- Instrument manufacturer/models and export format (example files with invented or approved nonconfidential content).
- Whether the target is intact-mass, peptide mapping, MS/MS, impurity characterization, or merely traceable data management.
- Required sample identifiers, batch metadata, acquisition methods, calibration/blank details, and QC acceptance thresholds.
- Expected outputs and how laboratory scientists will determine pass/fail on known benchmarks.
- Responsibilities for data handling, scientific review, IP, licensing, and deployment environment.

**Engineering strategy:** build stable import/provenance functionality first, then iterate in short acceptance cycles with laboratory scientists. No live lab integration, customer dataset, or scientific performance claim is authorized by this code.
