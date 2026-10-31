# INTENT Experiment Mini: guarded local engineering milestone

This adds an optional, experimental numerical controller to the existing MS pilot and full desktop. It is not the larger INTENT-R architecture or an LLM. It makes no claim of laboratory prediction accuracy. The scientific workflow remains available with predictions and learning disabled.

The complete architecture checklist is [research-intent-checklist.md](roadmaps/research-intent-checklist.md). Discipline navigation, central provider settings, institutional identity, shared-server login and realtime collaboration remain later milestones.

## What runs now

The **INTENT (experimental)** tab can initialize a random local model, configure its explicit feature/target schema, commit prospective predictions, accept separately signed measurement evidence, freeze holdout outcomes, run a numerical worker, evaluate candidates, manually promote an eligible candidate and restore a previously active checkpoint. No model or training job is created automatically. Predictions and learning default off and remain independent of the existing assistant switch. These controls are enforced by the controller as well as the UI; central application/provider policy is separate future work.

A model is bound to one project and immutable schema. Each feature names its unit, offset and scale; bounded normalized features are numerical inputs only, without inferred biological meaning. The measured target declares its own unit, offset and scale. An example three-input, sixteen-hidden-unit model has 81 learned parameters. The architecture is `intent-experiment-mini-v2`: tanh hidden layer, sigmoid scalar output, SGD, bounded replay, explicit seed and saved random state. It is intentionally distinct from the supplied retrospective demonstrator, whose checkpoint is never imported automatically.

A prediction requires an active planned experiment with no existing scientific observations. Genesis records its checkpoint, schema, conditions, encoded features, declared independent group, PREDICTED state and unavailable uncertainty before the measurement. Predictions never create experimental observations.

## Eligible measurement and signed review

A separate observation must already exist in the experiment store with `MEASURED` provenance and `VALID` quality. Its bounded JSON artifact is hashed and follows `MeasuredOutcome` in `virtual_lab/intent/schema.py`:

```json
{
  "format": "intent-measured-outcome-v1",
  "experiment_id": "existing-experiment-id",
  "schema_sha256": "64-lowercase-hex-characters",
  "group_id": "independent-study-or-acquisition-group",
  "value": 0.5,
  "unit": "the target schema's exact unit",
  "acquired_at_utc": "2026-10-30T12:00:00+00:00"
}
```

The artifact's acquisition time must match its observation, follow the committed prediction and not be in the future. Unknown MS imports, simulated/calculated outcomes, predictions and workflow approvals are ineligible. A signed human assertion establishes the reviewed scope; the software cannot independently prove instrument origin or group independence.

The review envelope has exactly `review`, `public_key` and `signature` fields. The review names the model, project, experiment, prediction, observation, artifact SHA-256, schema SHA-256, independent group, `train` or `holdout` purpose, reviewer identity, explicit `permitted_data_use: true`, and an expiry no more than 30 days ahead. The signature is Ed25519 over the canonical JSON of the validated `Review.model_dump()` (sorted keys, compact separators, finite values). It must match a trusted `HUMAN_APPROVAL` key and signer identity in the existing trusted-signer registry. Both bundled demonstration keys are explicitly refused. No private signing keys are stored by this controller.

**Institutional reviewer provisioning is not implemented here.** The stock registry contains only demonstration identities, so the shipped defaults cannot authorize real training. An institution must establish a genuine trust anchor and reviewer workflow before research use. Automated tests register ephemeral keys only inside isolated fixtures; they do not add a production reviewer or convert the BSA data into trusted labels. Trust status, expiry, observation quality and artifact bytes are rechecked before updates and evaluation. Expired reviews require renewed authorization through a future institutional review workflow; the controller deliberately refuses continued use meanwhile.

## Candidate lifecycle and limits

Only one accepted outcome per experiment and declared acquisition group contributes to a model. This prevents treating successive BSA scans as independent experiments. Five or more explicitly reviewed independent holdout outcomes must be frozen before the first update; this minimum is a software gate, not a scientifically sufficient sample-size claim. Holdout observations never enter replay.

Training requires both the learning switch and project permission. A separate CPU process receives only bounded JSON numerical state, one authorized outcome and bounded replay. The GUI remains responsive and supports cancellation and a 30-second timeout. The worker blocks network sockets and loads no LLM/provider. It is a trusted built-in worker, not an OS sandbox for arbitrary user code. Cancellation, crash, startup failure, revoked permission and stale candidate state cannot activate a checkpoint. A crash may leave an unreferenced checkpoint file; only a ledger-committed hash can be loaded. Jobs are transient and are not automatically retried on restart.

Checkpoint envelopes are content-addressed immutable JSON. Shape, size, finite bounds, architecture, configuration, replay lineage, pre-update metrics and digests are checked. Saved state includes weights, RNG state, replay, optimizer identity, update count, schema and parent checkpoint. The workspace writer lease protects local commits. This is a single-computer ownership mechanism, not cross-workstation concurrency or institutional authentication. A user with control of the OS and ledger files remains outside this local trust boundary.

Updates create candidates only. Promotion reevaluates the current candidate against the frozen holdout, requires no worse MAE than the active checkpoint and strictly better MAE than the mean of signed training outcomes. It requires an explicit action and records that scientific validation is false. Restoration can activate only a previously active checkpoint and also resets the training parent to that point. The ledger retains all earlier updates and evidence, including discarded branches. No calibrated uncertainty, broad generalization, drift monitoring or automatic model promotion is claimed. Repeated holdout evaluation must be governed by the eventual laboratory validation protocol.

## BSA verification and reproducible commands

The supplied archive is retained outside Git. Inspection preceded execution; its five tests and replay were run in a separate copy. The HUPO-PSI indexed mzML definition was checked against the [official schema](https://github.com/HUPO-PSI/mzML/blob/master/schema/schema_1.1/mzML1.1.1_idx.xsd). The repair changes the wrapper index pointer and placeholder checksum, leaving the mzML document and decoded measurements intact. Comparison with the [upstream OpenMS example](https://raw.githubusercontent.com/OpenMS/pyopenms-docs/master/src/data/BSA1.mzML) matched all 1,684 spectra and 479,455 peak pairs. Removing the upstream file's final LF matches the supplied original-file digest.

The three extracted peak lists contain 467, 478 and 102 peaks. They belong to one acquisition and are imported into one experiment with a shared sample/group label, relative scan-time attribution and unspecified absolute acquisition time. The scan-summary table is rejected by the strict spectrum importer. The BSA workflow retains UNKNOWN evidence, even after workflow review. Reprocessing, isolated alteration detection, traceability, plotted reports, companion JSON and detached checksums use the existing MS services. The portable study contains MS evidence; INTENT model state and permissions are local and are not silently transferred by study import/export.

```bash
python -m scripts.verify_bsa_workflow --archive /path/to/VirtualLab_BSA_Repaired_And_INTENT_Online_Prototype.zip --output /new/local/evidence-directory --pdf
QT_QPA_PLATFORM=offscreen VIRTUALLAB_BSA_ZIP=/path/to/archive.zip python -m pytest tests/intent tests/pilots/test_bsa_reference.py -q
```

No archive scripts run in this verification command, and no dataset is downloaded. It verifies the reviewed repaired mzML/CSV digests, all 1,684 index entries, indexed SHA-1, reconstructed original SHA-256 and workflow acceptance. The independent upstream binary-array comparison is recorded separately in the local review evidence.

The supplied sequential replay reproduced approximately 0.061884 pre-update MAE against 0.173310 for its historical-mean baseline after 100 scans. This is retrospective pattern learning within one acquisition, not prospective laboratory performance. Its final weight hash differed from the supplied run under the local Python 3.12 environment; approximate metrics were reproduced, not cross-environment bit identity. The new controller tests use separate synthetic fixtures and do not learn from these scans. A scientifically meaningful outcome, independent experiments, explicit training rights, institutional keys, target-OS acceptance and hosted CI remain release/validation prerequisites.
