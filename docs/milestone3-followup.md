# Milestone 3 follow-up before Milestone 4

This follows the evidence review's request for native macOS GC stress and presentation refinements. Milestone 3 remains a locally verified source milestone; the original navigation branch is preserved for review. This follow-up does not implement the unified provider/settings architecture.

## Presentation

Home now uses native Qt vector discipline icons, explicit Available/Experimental/Unavailable badges and installed-tool summaries. Tiles use two columns on smaller windows and three on wider windows. Unavailable disciplines remain disabled. Recent projects display their discipline, experiment count and whether they were previously opened. Project names render as plain text, with list keyboard selection preserved.

An empty discipline library now gives Create Project and Import Study guidance instead of displaying a large empty list. Search with no results offers a clear-search action. Existing project creation, domain reassignment, study import and saved context continue through the same study services.

A permanent Settings entry opens a read-only overview of the local workspace, presentation profile, assistant session and INTENT switches. Its link opens existing INTENT controls for the current project. Opening the overview does not enable AI, change learning policy or initialize a provider. Unified editable preferences, provider management and service-level routing policy remain Milestone 4.

The review also found an active-work navigation bypass in the notebook: its Open/Create experiment, Return to staging and Import buttons previously called study activation directly. Those UI paths now share the navigation guard, checked before reads or durable mutations. This remains a local workflow guard, not an authentication or multi-user permission boundary.

## Native stability method

`scripts/stress_navigation.py` creates a fresh synthetic workspace and one QApplication. Each cycle runs an actual numerical simulation worker while another worker allocates reference cycles, exercises the unchanged one-second GUI GC timer, switches between projects, restores results and verifies scope, closes/reopens the full desktop, and checks artifact hashes. It confirms AI/INTENT learning and instrument listeners remain inactive. Workers join before teardown, and explicit QApplication destruction checks restoration of the original Python GC policy.

The driver does not lower GC thresholds or force collection for the long native runs. It records actual Qt platform, Python/PySide/Qt versions, collection thread IDs, cycle counts, hashes and failures in JSON/JSONL. Python network and credential-store operations are blocked. The existing RHO viewer intentionally rejects nonlocal fetches; only that exact console diagnostic is retained separately from unexpected critical messages. RHO rendering is not validated. Other unexpected Qt critical/thread-affinity messages, Python callback failures, assertion failures and native crashes fail the run.

Completed local native runs used the macOS `cocoa` platform:

| Environment | Cycles | Actual simulations | Result |
| --- | ---: | ---: | --- |
| Python 3.11 | 30 | 30 | Passed |
| Python 3.12 | 20 | 20 | Passed |

All observed cyclic collections ran on the GUI thread. All generated artifacts were reverified, and GC policy restoration passed after application teardown. These bounded synthetic runs support the mitigation in this environment; they do not establish indefinite stability, Windows readiness, RHO rendering correctness or laboratory acceptance.

```bash
QT_QPA_PLATFORM=cocoa python scripts/stress_navigation.py --cycles 30 --dwell-ms 1250 --output /new/local/stress-directory
QT_QPA_PLATFORM=offscreen python -m pytest tests/gui/test_navigation_stress.py tests/gui/test_project_context_guard.py tests/gui/test_navigation_presentation.py -q
```

The native driver needs normal local Qt/WebEngine IPC. A managed macOS sandbox blocked Chromium startup before the short test; it was rerun outside that restriction in an isolated workspace. That startup denial is not counted as a completed stress cycle. No provider, real instrument or laboratory data is used.

Full local regressions, short stress tests, screenshots and native result records accompany the local evidence packet. Source datasets and runtime workspaces stay outside Git. The existing hosted CI billing gate, independent usability testing and laboratory/target-OS acceptance remain separate outstanding items.
