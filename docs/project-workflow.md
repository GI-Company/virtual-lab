# Research projects and portable studies

The Projects workspace supports research questions independent of the built-in RHO model.

1. Create a named project.
2. Enter an experiment name and research question, then create and open it.
3. Choose a registered model in Simulation, or run AlphaGenome or AlphaFold DB in Computational Biology. New results attach to the experiment selected at submission, even if selection changes while the request runs.
4. Use Projects to attach older unassigned results, inspect saved protocols and outputs, and verify artifact hashes.
5. Reopen the app to restore the active experiment. Select a saved simulation to restore its analysis; switching experiments clears the prior analysis.
6. Enter an absolute path ending in `.vlab-study` and export. A recipient can paste that path or drag a local study file into the path field, then import.

Study exchange uses an inline path field because Qt 6.11's macOS accessibility bridge crashed during QFileDialog traversal on the tested macOS 27 system. No accessibility or system security protections are disabled.

## Package contract

Version 1 is a ZIP containing `study.json`, experiment/project metadata, observation metadata, and the referenced result artifacts. SHA-256 checks cover each artifact and computational manifests retain their original bytes. Imports reject unsafe paths, duplicate entries, oversized archives, missing/mismatched files, conflicting experiment/result identities, and invalid relationships. Existing studies are never overwritten. Imported studies use local copies of artifacts and do not require the source filesystem.

This is an unsigned research snapshot, separate from legacy signed `.vlab` bundles. Byte integrity does not prove publisher identity, original execution, scientific correctness, or biological efficacy. Import records identify the unsigned origin when preparing prediction context for research assistance. The original complete ledger is not transferred.

## Scope

- AlphaGenome and AlphaFold DB support general research projects.
- Simulation supports RHO P23H and generic gene expression; see [model extensions](model-extensions.md). RHO reference remains model-specific.
- The experiment schema migrates existing databases additively. Legacy observations without file references remain visible but cannot pass export verification.
- Project/experiment switching, assignment, export/import, and simulation artifact ownership have regression coverage.
- Study packages are capped at 100 MB and 1,000 entries. Version 1 supports a snapshot import into a separate workspace; merging existing experiments is not supported.
- The wider legacy application's working-directory-dependent runtime ledger and version consistency still need normalization before a production release.

## Local verification

```sh
QT_QPA_PLATFORM=offscreen python -m pytest tests/projects tests/computational tests/core/test_ledger.py tests/core/test_artifact_registration.py tests/test_nested_manifest_bundle.py -q
python -m pip wheel --no-deps --wheel-dir dist .
```

The cockpit extra now declares the tested Vertex ADK, system monitor, and WebSocket dependencies. The build explicitly includes the `virtual_lab` namespace package.

See [measurement calibration](calibration.md) for the separate published-data fitting and held-out evaluation workflow.
