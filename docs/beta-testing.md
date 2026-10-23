# VirtualLab security beta

These branches are opt-in beta candidates. Main and existing production research folders are not changed.

| Branch | Packaged default | Presentation |
|---|---|---|
| `codex/beta-core` | researcher | Full researcher cockpit |
| `codex/beta-high-school` | high-school | Guided gene-expression lab, fixed model assumptions, AI disabled in the UI |
| `codex/beta-undergraduate` | undergraduate | Teaching lab with editable assumptions and optional AI |
| `codex/beta-graduate` | graduate | Full tools with graduate research guidance |

All branches share the same scientific, security and provenance implementation. Edition settings simplify presentation; they are **not** an access-control or parental-control boundary. The high-school profile is an initial supervised teaching interface, not a complete curriculum or managed classroom product. Students write their own hypothesis, plan, interpretation and limitations. No tutorial writes assessed research for them.

## Install and start

Use Python 3.10–3.12 for the published CI targets, a fresh virtual environment and the desired branch:

```sh
git clone https://github.com/GI-Company/virtual-lab.git
cd virtual-lab
git switch codex/beta-high-school
python -m venv .venv
# Activate .venv using your operating system's activation command.
python -m pip install '.[cockpit]'
python -m virtual_lab.main
```

Add `.[cockpit,ai]` only for optional Gemini assistance. Network services and physical equipment are not needed for the manual research workflow. A separate install is not needed to preview profiles: set `VIRTUALLAB_EDITION` to `researcher`, `high-school`, `undergraduate`, or `graduate` before launch.

Default storage is `VirtualLab/beta/<edition>` under the operating system's application-data directory. `VIRTUALLAB_DATA_DIR` explicitly overrides that location. Do not point a beta at production research storage. Import a copy of a `.vlab-study` export through Projects instead. Existing cockpit folders are not automatically migrated, deleted or rewritten.

## Tester exercise

1. Create a project and experiment. State a testable model question.
2. Write a hypothesis, method, expected outcome and acceptance criteria.
3. Choose the gene-expression model, run a zero-exposure scenario and an exposure scenario with matching seed and assumptions.
4. Inspect trajectories and endpoint distributions. Compare both records and open the numerical certificate.
5. Export the CSV. Write a conclusion with citations to the saved results and explicit limitations.
6. Export a `.vlab-study`, restart, then import into a second scratch workspace. Check the plan, observations, conclusion and artifact verification.

A numerical certificate checks a limited numerical comparison, not experimental validity. Parameter uncertainty is assumed. All simulated results remain SIMULATED. Imported unsigned files do not establish a trusted instrument or biological effect.

## Security changes shared by every edition

- The repository's exposed demonstration publisher key is revoked for both bundles and programs. Bundle signing has no fallback private key. Old bundles signed by that key intentionally fail authenticity checks; historical study packages remain independently importable as unsigned byte-consistent research exports.
- New ledger entries use schema 2.0 and RFC 8785 canonical JSON. Historical schema 1.0 entries retain their original Python JSON encoding, including the two historical zero representations. Verification selects the historical encoding without rewriting or rehashing rows. Unrecoverable old actor metadata causes an explicit integrity failure.
- Legacy `ledger.db` is verified read-only and displayed alongside `genesis.db` with distinct source/event identities. New writes use `genesis.db`. Histories are not spliced into a fabricated single chain.
- Approval execution requires a persistent ledger, full signed proposal envelope, timezone-aware validity period, passed rule record, exact recorded signature and trusted human signer. A serialized durable claim is committed before a side effect. Failed or interrupted callbacks remain consumed and need operator reconciliation plus a newly signed proposal. This is at-most-once admission, not an exactly-once guarantee for external equipment.
- Legacy tools and alternate unsigned agent execution paths fail explicitly. They never claim an action or ledger write occurred.
- Timestamps are covered by provenance hashes. A separately named content fingerprint serves reproducibility.
- Bundle creation snapshots committed SQLite WAL data, excludes its output and WAL sidecars, and stages replacement atomically. New bundle/program manifests declare their canonicalization.
- Installed Python model extensions do not execute at application startup. Explicit trusted-code opt-in still runs with the user's privileges; it is not a sandbox.
- Ensembles perturb the four declared RHO controls, then derive internal rates. Previous simulation artifacts retain their original bytes and interpretation; new runs intentionally use the corrected perturbation scope.

## Publisher and human trust

A signing key must be supplied explicitly using `VLAB_PUBLISHER_SK` (bundle) or `VLAB_PACKAGER_SK` (program). Provision private keys outside the repository. Never send them to an AI provider or store them in a study package.

Trust is a separate operator decision. Set `VIRTUALLAB_TRUST_STORE` to a protected local JSON file; public keys alone belong in that file:

```json
{
  "format": "vlab-trust-v1",
  "signers": [
    {
      "signer_id": "your-publisher-id",
      "public_key_hex": "REPLACE_WITH_64_HEXADECIMAL_PUBLIC_KEY_CHARACTERS",
      "roles": ["BUNDLE_PUBLISHER"]
    }
  ]
}
```

Other explicit roles are `PROGRAM_SIGNER` and `HUMAN_APPROVAL`; grant only the needed roles. Packages cannot enroll their own signers. The compromised demonstration publisher cannot be restored through this configuration. Malformed stores fail closed. Protect the trust file and research directory with OS permissions. This desktop beta does not protect against an attacker who controls the OS account or rewrites both a local ledger and its trust configuration.

## Test scope and release gates

The accompanying local verification covers the full AI-free study flow for all three student profiles, researcher flow, CSV/study round trips, schema-1 compatibility, approval restart/concurrency, real adapter calculations, local HTTP assistant traffic, paired transport routing and workspace layout tests. No production research data is modified.

Remaining gates before a general or instrument-connected release:

- Real hardware validation and client support for the pairing protocol; no physical device has been certified.
- Vendor adapters, sample identity assurance, calibration traceability, acquisition replay handling and authenticated remote transport. The current receiver is loopback-only. LAN discovery/unauthenticated network control are not supported by this beta.
- Integration of extension results into the desktop study notebook/export workflow. The CLI currently writes a separate result artifact with a ledger anchor; it does not silently add it to a scientific conclusion.
- Real provider/model compatibility tests for each configured AI endpoint; this verification uses an offline local provider, not a live cloud run. No arbitrary weights or file formats are supported by inference.
- A passing hosted CI run on supported Python versions and packaging platforms. Previous hosted runs were blocked by GitHub account billing; local results do not substitute for those platform checks.
- Optional MLX/model-weights, pandas/AlphaGenome, Kotlin interop and live cloud checks omitted from the local suite remain unverified where skipped.
- Publisher onboarding, key rotation, external anchoring and operator recovery procedures need an operational review. Unsigned study packages provide byte integrity, not authenticated authorship.

This batch is not a claim that all 38 original audit findings have been independently closed.
