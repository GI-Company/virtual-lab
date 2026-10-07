# Growth-response timing audit

`virtual_lab.biology.timing.growth_slowdown_frame` detects a sustained drop in fractional length growth. It requires finite contiguous frame data covering frames 10–90, computes reference growth over frames 10–30 and searches frames 31–90 for five consecutive values at or below half the reference. It returns an explicitly labeled physiological proxy; a missing event returns `None`, not an invented timestamp. Positive reference growth is required.

In the archived mEGFP analysis, a primary requirement of three eligible cells per colony/frame failed in one training colony. The primary result remains blocked by coverage. A separately documented exploratory analysis allowed one eligible cell, retained all four colony weights, and located a slowdown proxy at frame 45. The derivative used each cell's own unsmoothed length at frame ±2, avoiding division-boundary differences.

A paired-cohort fluorescence reanalysis changed the effective half-time from 10.71 minutes at baseline frame 61 to 13.58 minutes at baseline frame 45. Baselines also change normalization and duration, so fit metrics do not constitute a model-ranking comparison. The previously held-out outcomes were already inspected: this is retrospective re-evaluation, not new independent validation. No rate or saved biological object was replaced.

The delivery in `outputs/maturation-timing-audit` contains the frozen plan, coverage amendment, contributor counts, source hashes, complete paired results, plot, source audit and reproducible scripts. All eight matched 37 C recordings inspected share one acquisition date. Neither differently conditioned files nor purified-protein assays were treated as matched independent validation.
