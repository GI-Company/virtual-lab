# Measurement calibration

Open an experiment in Projects, then choose Calibration. Fit the bundled PGK1 benchmark or a local CSV, inspect the fitted curve and held-out residuals, save, and export a `.vlab-study` in Projects. Select a saved calibration in Projects to restore its plots. This workflow is separate from the Simulation model selector.

## Local measurements

CSV header: `sample_id,replicate,split,time_min,value`. Declare gene/organism/condition, source, and linear or log2 scale in the GUI. Each biological replicate belongs to exactly one split (`train` or `holdout`), includes time zero, and has at least two distinct positive times. IDs must be unique; values finite; linear values positive. Limits: 1 MB, 6–1000 rows, times 0–2880 minutes. Local declarations are not independently verified.

Each replicate is divided by its own arithmetic mean baseline in linear space. Log2 inputs are converted before normalization. The held-out baseline is therefore observed conditioning information. Time-zero points are excluded from fitting and all reported error metrics.

## Fixed fitting specification

The model is `m(t) = exp(-k*t/60)`, with time in minutes, k in inverse hours, and fixed `m(0)=1`. Only training positive-time points determine k through unweighted least squares, bounded to 0–120/h with explicit endpoint evaluation. Half-life is `60*ln(2)/k`; zero decay gives an unbounded half-life. Positive-time holdout values never affect fitted parameters. RMSE, MAE, R², and the no-decay baseline error are reported separately by split. No pass threshold or confidence interval is inferred from this single training biological replicate. An independent DOP853 integration checks numerical agreement with the analytic exponential; that is not biological validation.

## Published benchmark and result

Source: [Shalem et al. (2008), Molecular Systems Biology 4:223](https://pmc.ncbi.nlm.nih.gov/articles/PMC2583085/), DOI 10.1038/msb.2008.59; Supplementary Table 1, `msb200859-s2.xls`, sheet 1, Excel row 642 (YCR012W/PGK1). Zero-based columns 13–21 train; columns 52–57 hold out reference2. The bundle includes 15 author-normalized values, extraction code, source hashes, and provenance metadata. PGK1 was selected before fit quality was known.

Computed result: k=1.1189618316/h, half-life=37.167336 minutes; training RMSE=0.0679437 (8 points), holdout RMSE=0.1698390 (5 points), holdout R²=-2.791935, no-decay holdout RMSE=0.4227340. The fitted curve improves on constant abundance 1 but performs worse than the held-out mean by R². The held-out mean is a retrospective comparator, not a deployable prediction. No biological success is claimed.

The author table lists a training half-life of 42.908823 minutes. This fixed-initial-condition fitting specification does not reproduce that reported estimate, and it was not tuned to match it. A preliminary transformation of GEO processed intensities did not reproduce the supplemental curves; the benchmark therefore uses explicitly normalized supplement values. That discrepancy remains unresolved. This is a same-study replicate check, not an independent laboratory replication or a new wet-lab experiment. Rates do not automatically transfer to proteins, drug response, humans, or the generic gene-expression simulator.

## Persistence

Saved JSON includes input values, normalized values, predictions, residuals, splits, metrics, source metadata, fitting specification, and implementation SHA. Rates are INFERRED and curves SIMULATED. Study export embeds the result artifact and checks hashes on import. Hashes verify bytes, not scientific validity or publisher identity. New calibration quantity identities are scoped to dataset metadata to avoid treating different biological contexts as interchangeable.
