# Frozen maturation evaluation

Calibration → Maturation validation evaluates an explicit frozen model against a dataset manifest and adjacent CSV. It does not fit rates or change biological objects. Open an experiment in Projects, enter absolute paths to the model and dataset JSON, evaluate, save, and export a study. Select the saved result in Projects to restore it after restart.

The model declares reporter, host, strain, temperature, assay, training acquisitions, rate, initial immature/mature ratio, and supported duration. Each acquisition includes an identity, source identifier, date, original source-file SHA256 values, biological-unit identity when known, event time, timing basis, and timing source. The dataset additionally declares prior inspection, synthetic status, processing, CSV name, and CSV hash. CSV columns are `acquisition_id,series_id,time_min,fluorescence`. Times share the event's minute origin; fluorescence is positive, finite, and in consistent units within each series.

Eligibility and accuracy are separate outputs:

- `CANNOT_ALIGN`: an event time or measured event-time baseline is absent, or there are fewer than three subsequent measurements. No automatic onset selection, interpolation, or partial-series metric is performed.
- `EXPLORATORY_ONLY`: alignment is possible, but overlap, context mismatch, unsupported duration, uncertain timing, missing biological identity, prior inspection, or synthetic inputs prevent eligibility.
- `ELIGIBLE_BY_DECLARED_METADATA`: the supplied declarations pass these checks. This is neither authenticated independence nor biological validation. Identities, source hashes, timing evidence, model provenance, and prior inspection remain researcher declarations.

Training/evaluation overlap checks use acquisition IDs, source/date pairs, biological-unit IDs, and source-file hashes. Same source/date is conservatively excluded even if separate runs might have occurred that day. Hash checks establish byte consistency, not publisher identity. The source-report hash is a reference; the application does not authenticate the original fitting report or acquisition source files.

Fluorescence is divided by each series' measured event-time value. Predictions are `1 + A * (1 - exp(-k*t))`, with frozen k and A. Pooled metrics weight time points equally; per-series metrics are also stored. Time points are correlated and are not independent biological replicates. This narrowly scoped one-step model assumes no new protein production and no relevant degradation. It does not infer individual molecular behavior or validate a whole-cell simulation.

Saved CALCULATED reports embed the complete model, manifest, measurement CSV, exclusions, metrics, and normalized predictions. Restore/import recomputes results from embedded inputs and rejects disagreement. CSV is limited to 1 MB/10,000 rows, constrained to the manifest directory, and hash checked. Nonfinite measurements, duplicate time points, invalid IDs, unsupported normalization ranges, and duplicate training acquisition IDs are rejected. Reports can be saved when alignment or eligibility fails so the reason remains in the study.

## Public-data demonstration

The published mEGFP/MG1655/37 C data from DOI 10.7910/DVN/KBNK6R reproduce the prior retrospective error: RMSE 0.0135344348883, R² 0.8737279691, four colony series, 420 positive-time points, one declared acquisition. Rate 3.9193393476/h and initial ratio 0.1632029783 remain frozen. This is effective post-frame-61 relaxation; the nominal baseline is not a verified translation-arrest time.

The result is EXPLORATORY_ONLY: training and held-out files share acquisition date/identity, biological-unit separation is unresolved, intervention timing is nominal, and outcomes were already inspected. No new matched independent acquisition is claimed. Public data only were used; private data and credentials are unnecessary.

Validation: 183 targeted regression tests passed, including 31 new evaluation tests. The native GUI was exercised through project creation, evaluation, save, export, restart, and restore. The final GUI-exported study was independently imported into a fresh local store and recomputed. Artificial fixtures test eligibility mechanics only and are not delivered as biological evidence.
