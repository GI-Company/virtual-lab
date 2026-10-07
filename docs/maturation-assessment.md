# Published-data maturation assessment

`virtual_lab.biology.maturation_validation` provides training-only fitting and held-out-colony evaluation of `F(t)/F(0) = 1 + A(1 − exp(−kt))`. Each training colony has equal objective weight. Twelve fixed initializations are used with bounded least squares. Held-out fluorescence contributes only to evaluation; each colony is normalized by its own initial baseline, not its future plateau.

The Balleza mEGFP 37 C assessment uses eight CC0 MATLAB colony recordings from [Harvard Dataverse](https://doi.org/10.7910/DVN/KBNK6R). Four colonies in FOV001–003 train; four in FOV004–005 are held out. All recordings have the same acquisition date. The source paper is [Balleza, Kim and Cluzel, Nature Methods](https://pmc.ncbi.nlm.nih.gov/articles/PMC5765880/).

The analysis plan was saved before aggregate fitting. Complete unsmoothed cell fluorescence tracks spanning frame 61 through 166 were selected without fluorescence-based exclusions. This conditions the analysis on surviving, non-dividing tracked cells. There are 41 selected cells in training and 63 in holdout, summarized into four colony curves per group. The 420 positive-time points per group are correlated observations, not 420 independent replicates.

The primary effective rate is 3.919339348/h, with capacity A=0.163202978 and effective half-time 10.611184 minutes. Held-out RMSE is 0.013534435 and R² is 0.873727969 in own-baseline-normalized fluorescence. The actual biological object simulator reproduces those metrics. The no-maturation baseline RMSE is 0.138339073.

## Timing limits the biological interpretation

The primary start was frozen at frame 61 using the paper's nominal one-hour acquisition schedule. A subsequent diagnostic found earlier slowing of selected training-cell length traces. The precise arrest frame is not annotated in the structures used here, and nominal timing is therefore unreliable for identifying the complete maturation response. The source paper used cell-growth information to identify arrival more precisely.

The primary fit was not retuned. Shifting the analysis baseline by five minutes in either direction changes the effective half-time to 9.551505–11.378503 minutes. This sensitivity range is not a confidence interval. A high within-acquisition R² does not resolve the timing uncertainty or establish an independently validated maturation constant.

`fitted_system` maps the effective parameters into a scoped `maturing_gene_expression` probe: mature protein starts at one normalized unit, immature protein at A, maturation is k, and production and turnover are zero. The inferred rate and immature pool retain a SHA256 reference to the assessment report. The study must be distributed alongside that report; the study package itself does not embed the external assessment JSON or raw MATLAB files. Ordinary new-system defaults remain unchanged.

The delivered study was imported and restored through the native GUI. Its name and conditions explicitly identify an effective post-baseline model with unresolved arrest timing. The empirical fit is currently a reproducible research workflow, not a new general-purpose maturation calibration tab.

Before broader use, resolve exact arrest timing, verify lineage/selection assumptions, and test on independent acquisitions with matched conditions. No independent-laboratory, whole-cell, sequence-derived or clinical validity follows from this assessment.
