# Computational Biology

Open Virtual Lab and select **Computational Biology**. The workspace connects remote computational instruments to the existing experiment observation store and Genesis ledger.

## Setup

Use the Python environment that launches Virtual Lab:

```sh
python -m pip install -e '.[biology]'
./start_virtuallab.sh
```

AlphaGenome uses the official 0.9 SDK. Save its API key with **Save key** in the AlphaGenome panel. Credentials use Virtual Lab's operating-system credential store (`virtuallab` / `alphagenome`), never experiment JSON, source files, command-line arguments, or environment variables. On this Mac, the supplied key was already saved in Keychain and a live request succeeded.

AlphaFold DB requires no key, local inference installation, or database mirror. Each request accepts exactly one UniProt accession. The default is metadata only. The optional mmCIF and PAE checkboxes fetch only the selected protein's files, with limits of 16 MB and 32 MB respectively. No FTP, batch, or bulk-download route exists. Returned URLs must use the official AlphaFold HTTPS host; redirects are rejected.

Research reasoning continues to use Virtual Lab's existing Vertex API integration.
When you send a research request, up to five recent computational observations from the active experiment (or unassigned staging) are verified against their ledger anchors and included as bounded prediction summaries. Raw arrays and input DNA sequences are not added to the Vertex prompt. Corrupt or unanchored artifacts are excluded. The agent is instructed to cite run IDs and preserve the distinction between prediction and measurement.

## Assays

AlphaGenome supports reference intervals, sequences, REF/ALT variants, variant scoring, and bounded in-silico mutagenesis. This first adapter uses **human hg38** only. Windows are exactly 16,384, 131,072, 524,288, or 1,048,576 bases. Intervals are 0-based and half-open; variant positions are 1-based. Enter VCF-style anchored alleles for indels. The complete reference allele must be inside the selected window.

The adapter does not independently compare your REF allele with hg38. AlphaGenome substitutes the supplied alleles, so check reference alleles before interpreting a variant result. REF/ALT track summaries are descriptive statistics, not calibrated biological-effect scores. Use variant scoring for the SDK's modality-specific scoring methods, and inspect the saved gene and track annotations.

Predictions can be restricted using comma-separated ontology identifiers such as `UBERON:0002048`. Scoring and ISM use the SDK's recommended scorers and return all tracks; their API does not take an ontology filter. ISM is limited to 32 bases (up to 96 substitutions), with two parallel SDK requests. Large windows and broad tissue selections can produce large AlphaGenome outputs; start with a small window and a single tissue.

The GUI runs each assay in a separate process, remains responsive, and offers cancellation. A five-minute deadline terminates unresponsive runs. Cancelled or interrupted jobs are not registered; a force-killed worker can leave a `.partial` folder, which is excluded from saved results. The direct Python adapter has SDK/HTTP connection timeouts but should be run in a supervised process for an overall execution deadline.

## Results and provenance

An active experiment is captured when the run starts. Changing the selected experiment during a request does not redirect its result. Without an active experiment, the observation enters the existing staging area.

Complete bundles live under `$VIRTUALLAB_DATA_DIR/computational/`, or `~/Library/Application Support/VirtualLab/cockpit/computational/` by default. Each contains a manifest with the validated request, hypothesis, assembly, context, instrument, model selector/version, timestamps, limitations, and SHA-256 digests for all artifacts. AlphaGenome arrays are compressed NumPy files readable without pickle; separate JSON files preserve track metadata, intervals, resolutions, junction identities, or scorer/gene annotations. AlphaFold preserves the raw API metadata and any requested files.

The manifest digest is anchored in the existing Genesis ledger. Saved runs can be selected in the workspace and their hashes rechecked. The Provenance tab includes computational events and verifies their artifacts. If registration fails after an otherwise successful run, **Register saved run** retries idempotently; raw outputs are retained. Registration uses separate ledger and observation-store transactions, so this retry is also the recovery path after a partial registration.

AlphaGenome and AlphaFold observations are `PREDICTED`. They never become `MEASURED`. Model confidence does not establish causal effects or experimental validation. Gene-to-transcript-to-protein mapping and novel mutant structure inference are not automated in this integration. AlphaFold DB models provide reference structural context.

The AlphaGenome SDK version and explicit model selector are recorded. The API does not expose an immutable weight digest; a model selector alone cannot guarantee identical future predictions.

## Programmatic use

`GenomeRequest` and `StructureRequest` validate protocols independently of the GUI. Adapters implement an `execute(request, directory)` contract. `artifacts.execute` saves and verifies a completed bundle; `artifacts.register` attaches it to the supplied ledger and observation store on their owning thread.

```python
from virtual_lab.computational.requests import StructureRequest
from virtual_lab.computational.adapters import adapter_for
from virtual_lab.computational.artifacts import execute

request = StructureRequest(accession="P08100", hypothesis="Inspect reference RHO structure context")
run = execute(request, adapter_for(request))  # Metadata only by default.
manifest = run.read()  # Verifies the manifest and every artifact hash.
```

Sources: [AlphaGenome essential commands](https://www.alphagenomedocs.com/colabs/essential_commands.html), [AlphaGenome API](https://www.alphagenomedocs.com/api/generated/alphagenome.models.dna_client.DnaClient.html), [AlphaFold DB API](https://alphafold.ebi.ac.uk/api-docs).
