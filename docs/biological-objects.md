# Persistent biological objects

The Biological objects tab implements a first gene → RNA → protein system. Biological identity is separate from the mechanism that computes its state. The same object IDs survive successive experiment intervals, saving, restarting, and study export/import.

## Record structure

- Identity: stable object ID, label, organism, optional accession, sequence and variant, plus evidence. The GUI currently edits labels and organism; it does not edit the optional sequence fields.
- State: abundance, units, compartment and evidence. Gene copies and initial RNA/protein are assumptions; evolved RNA/protein states are explicitly simulated.
- Mechanism: versioned equation implementation, explicit object references, rates, units and assumptions.
- History: timed transcription/translation interventions, rationale and evidence; an experiment clock and revision number.
- Result: initial and final snapshots, trajectories, parent result ID, implementation hashes and limitations.

These are validated snapshots, not independently living biological entities or a complete virtual cell. Model records are validated again before simulation and persistence, including nested parameter mappings.

## First mechanism

For RNA abundance m and protein abundance p:

    dm/dt = transcription_rate × gene_copies × transcription_activity − RNA_decay × m
    dp/dt = translation_rate × translation_activity × m − protein_decay × p

Time is hours. RNA and protein have separate normalized abundance units; their numerical values are not directly comparable molecule counts. Translation rate converts normalized RNA to normalized protein per hour. Defaults are assumed, not calibrated or inferred from identity.

The solver uses a piecewise matrix exponential. An intervention changes its activity multiplier from its stated time onward. An event exactly at an interval's end affects subsequent intervals, not the preceding trajectory. Existing multipliers persist when continuing with no new intervention.

The original linear expression mechanism is retained alongside the maturation extension described below. It does not implement feedback, molecular binding, transport, resource limitations, stochasticity, cell division or sequence-dependent kinetics. AlphaFold/AlphaGenome results are not automatically converted into these rates. Naming a gene RHO, PGK1 or another label does not change its equations.

## GUI workflow

1. In Projects, create/open an experiment.
2. In Biological objects, enter identity/context, initial states and rates. Create the system.
3. Choose interval duration and optionally transcription or translation intervention, its time relative to the interval start and multiplier.
4. Run and save the result. Saving persists the complete snapshots and trajectory; a draft before its first saved run is not persisted.
5. Run another interval, or select a saved biological result in Projects and return to Biological objects to restore it.
6. Export the active study through the inline absolute `.vlab-study` path in Projects. Import it into another workspace to restore its results.

The GUI supports one new intervention per interval and fixes gene copies to one in its starter form. It supports either three objects or four with maturation enabled. The core supports up to 64 new events per run, with a bounded cumulative history. The graph shows the selected interval. Earlier results retain their own graphs. Restoring an older saved state can produce an alternative successor, but there is no dedicated branch visualization yet.

Continuation requires an exactly matching saved parent state in the same experiment. Study import verifies parent chains and artifact bytes before inserting records. Hash verification establishes byte integrity, not publisher authenticity or scientific validity.

## Verification and scope

Tests cover analytic RNA decay, comparison with a separate numerical ODE solver, protein behavior, interval continuation, event boundaries, translation inhibition, invalid records, altered states, persistence, study round trips and GUI integration.

The native GUI was exercised with transcription turned off at hour 2, saving at hour 4, restarting/restoring, continuing without another intervention and saving at hour 8. The exported package was imported into a fresh store and continued again.

A future extension should add a mechanism with an explicit biological scope and units, calibrate against appropriate measurements, then evaluate against held-out matched experiments. More training iterations cannot compensate for missing mechanisms. General cellular behavior remains future research.

## Extension: protein maturation and calibration transfer

The registry now also includes `maturing_gene_expression` version 1.0.0. Enable **Include immature → mature protein** before creating a new system. It adds a fourth persistent object: an immature protein pool. The existing `protein` object denotes the mature pool in this mechanism. Objects describe population-level abundances, not individual molecules.

For RNA m, immature protein u, mature protein p, and maturation rate k:

    dm/dt = transcription_rate × gene_copies × transcription_activity − RNA_decay × m
    du/dt = translation_rate × translation_activity × m − (k + protein_decay) × u
    dp/dt = k × u − protein_decay × p

Both protein pools share normalized protein units and the same degradation rate. Maturation transfers abundance between them. Stopping translation does not stop maturation of the existing immature pool. The mechanism is a one-step approximation, without a fluorescence measurement model, intermediate chromophore states, growth dilution or empirical parameter validation.

This choice is motivated by published reporter models; it does not import their rates. [Balleza et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC5765880/) report both approximately first-order and more complex reporter maturation kinetics. [Guerra et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC8938947/) distinguish one- and two-step maturation models in yeast. A single maturation step is therefore not a universal protein model.

In **Calibration**, save a fit and select **Create RNA-decay objects from saved fit**. The app verifies the saved artifact, reconstructs the training fit and holdout metrics, then creates a read-only RNA-decay probe in the same experiment. Its RNA rate remains INFERRED; resulting trajectories are SIMULATED. The complete calibration record is embedded and hashed so its data, split, metrics and source metadata travel with the objects.

Transfer requires structured gene, organism and condition metadata. The published PGK1 benchmark provides these fields. Existing free-text local CSV context alone is insufficient and is rejected with an explanation. The probe starts at normalized RNA one and protein zero, with production and protein turnover disabled. It deliberately isolates the calibrated RNA-decay process; it cannot silently turn that evidence into a calibrated maturation mechanism. Identity and conditions must remain those of the source dataset.

The GUI uses the source measurement span as its initial duration. Further continuation is possible, but simulation outside the observed time span is extrapolation. The calibration's holdout quality is not improved by transfer: the bundled example has holdout RMSE approximately 0.169839 and R² approximately −2.791935. Same-study holdout evaluation is not independent experimental validation.

Older three-object files remain readable. Optional fields default to absent, and lineage comparisons normalize these defaults before comparing saved snapshots. Older applications do not support the newly introduced maturation mechanism.
