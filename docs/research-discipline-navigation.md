# Milestone 3: discipline navigation and saved project workstations

VirtualLab now uses **Home -> discipline project library -> project workstation**, with the existing StudyService, ExperimentStore, Genesis Ledger and scientific widgets underneath. This is a local desktop source milestone, not a shared-server release or a change in scientific evidence classification. The [architecture checklist](roadmaps/research-intent-checklist.md) tracks the remaining work.

## Use the new interface

Start the full installed cockpit with `python -m virtual_lab.main --profile research`. The dedicated offline MS entry point remains `virtuallab-ms-pilot`; it supports the same `--profile research` and `--profile academia` choices. Both profiles use the same core, schema, evidence rules and safeguards. Academia currently changes the entry presentation; it does not claim a completed curriculum, classroom administration or separate institutional authorization.

Home lists Mass Spectrometry, Molecular Biology, Computational Biology, Physics & Simulation, Instruments & Sensors, Data & Research Analysis, and General research. The shared registry defines tool IDs, descriptions, default layouts and availability. A discipline with no installed primary tools is unavailable. For example, the offline MS installation enables its MS workflow and experimental INTENT while its other discipline tiles are unavailable; the full cockpit exposes its additional installed tools. The library lists each tool as enabled, experimental or unavailable. Availability describes installed software, not scientific validation, provider readiness or connected hardware. MS/MS compound identification remains explicitly unavailable.

Choose a discipline, search its project library, and create or open a project. The library can also import a verified `.vlab-study` package directly, without creating an unrelated empty project first. Create experiments from **New experiment / notebook**. The workstation experiment selector stays within that project. MS projects show the experiment notebook, MS Workflow, project provenance and experimental INTENT; unrelated full-desktop tools are reached explicitly through **Other tools in this project**. Opening an additional tool keeps the project and experiment context. It does not duplicate evidence or link observations from another project. Home offers search across local project names and a recent-project list; breadcrumbs remain visible in every navigation destination.

A project's discipline can be changed with **Move project** in its library. This changes presentation metadata and records a `PROJECT_DOMAIN_CHANGED` event. It does not rename IDs, move experimental records, alter measurements or grant training permission. Existing projects appear under General research until deliberately classified.

## What is saved and restored

The local query database records:

- A project's last active experiment, workstation tool and open time.
- Each experiment's selected notebook result, notebook page, selected MS run and MS page (Import, Spectrum, Original / normalized, or Provenance / review).
- The last Home, Library or Workstation destination for each presentation profile.

Reopening a project or restarting restores these saved selections. MS content is read through the existing hash-verifying dataset service. Result selections are checked against their experiment before inspection. Foreign/stale result references are refused; missing or altered dataset bytes leave the spectrum cleared with an integrity error. Unknown future view-page values fall back to a supported page, and a stale last-experiment reference falls back within the same project.

Saved research records and explicit view selections persist. Unsaved form drafts, graph zoom/scroll positions and running jobs are not resumed. Other computational or simulation input forms have not become complete domain-specific draft editors in this milestone. INTENT weights and active checkpoints keep their existing ledger-owned lifecycle; navigation does not promote a model or turn predictions into observations.

## Migration and portable studies

The SQLite migration adds `projects.domain_id` with the default `general`, plus separate local `project_context` and `experiment_context` tables. It does not reconstruct scientific tables or rewrite artifact files. When upgrading an occupied project store, it first creates a unique private `experiments-pre-domain-v1-*.sqlite3` metadata recovery snapshot beside the database. The snapshot is not a complete study backup: artifact files and the separate scientific ledger still form part of the workspace. Routine opens do not repeat the migration or overwrite earlier snapshots.

Version-1 study packages now preserve the declared project domain. Older packages without this field remain accepted and use General research for a new project; importing a legacy package into an otherwise matching existing project preserves its local classification. A conflicting supplied domain or unsupported domain is refused before durable import. Navigation selections, recency, provider settings and INTENT training permissions are not transferred by study export.

## Project isolation and side effects

Project and experiment switches clear active analysis, numerical/calibration/biological results and selection context. MS intake paths, source attribution, origin declarations, approval and review fields are cleared on context switches, including between two empty projects. Compare and computational history show only records belonging to the active project. Project provenance filters the displayed audit history while still checking the full ledger chain; imported-study and MS/INTENT events retain their recorded scope. Unassigned staging and the installed curated literature library remain explicitly separate from project-owned observations.

Leaving a project through the navigation controls is blocked while an experiment, computational/INTENT worker, assistant episode or instrument recording is active. Existing workers also retain their original experiment binding. Restoring an Instruments or optional AI view does not start a listener, connect hardware, initialize a provider or run a model. Instruments now exposes an explicit **Start instrument listener** action. The MS workflow and INTENT switches retain their independent behavior and default-off learning policy.

These are local presentation and persistence boundaries, not an authenticated access-control system. The workspace writer lease still permits only one writer for a local workspace. Shared-instance login, authorization, committed-change events, reconnect/conflict handling and realtime updates remain milestone 6; central AI/provider policy remains milestone 4.

## Verification

New tests cover additive legacy migration and its private recovery snapshot, unchanged project/experiment IDs and artifact bytes, domain reassignment and failed audit writes, legacy/new study roundtrips, scoped view references, recent/search behavior, empty-project intake clearing, unavailable tools, Research/Academia core reuse, tampered/stale dataset selections, two projects with multiple experiments, and real close/reopen restoration. A separate full-cockpit subprocess runs two actual synthetic simulations and checks Compare, computational history, audit and analysis isolation, saved result restoration, and absence of automatic AI/hardware activation after restarting into Instruments. The existing offline MS, INTENT, report-integrity and manual research tests remain part of the regression suite. Visual inspection also corrected spectrum layout so both axes and the numeric summary fit an ordinary workstation viewport.

A compatibility run exposed native `SbkObject_tp_traverse` failure during garbage collection on a simulation worker thread. The GUI now uses the existing pyqtgraph periodic collector, owned once by QApplication, to collect Qt wrappers on the GUI event loop; non-GUI numerical subprocesses retain their normal GC policy. A dedicated worker-allocation regression verifies collection thread identity. This follows the [Qt GUI-thread constraint](https://doc.qt.io/qtforpython-6/overviews/qtdoc-threads-qobject.html). The initial crash log and successful full/focused reruns are retained in local evidence rather than omitted.

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/projects/test_domains_and_context.py tests/gui/test_discipline_navigation.py tests/gui/test_discipline_navigation_flow.py tests/computational/test_workspace.py -q
```

Recordings and screenshots are actual Qt rendering with scripted interactions, not conceptual mockups. Source datasets, view-test workspaces and media remain in ignored local output directories. Local validation does not replace target-OS acceptance, laboratory validation or hosted CI; the existing GitHub billing lock remains an external release gate.
