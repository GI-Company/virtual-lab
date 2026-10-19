# Conduct a study without AI

Use a Python 3.10+ interpreter to create a virtual environment, then install the desktop extra:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[cockpit]'
python -m virtual_lab.main
```

On Windows, activate with `.venv\Scripts\activate` instead. Check `python3 --version` before creating the environment; use a newer Python executable if needed.

This installation does not require the Google GenAI or ADK packages, an AI API
key, a local language model, or a cloud account. AI assistance is off at startup.
The offline route below uses the included numerical models and local files.
Remote AlphaGenome and AlphaFold tools remain separate, optional research tools
with their own network/dependency requirements.

## Question and plan

1. In **Projects**, create a named project and create/open an experiment with a
   research question. Expand **Project and experiment setup** to switch or create
   another experiment after setup collapses.
2. In the right-hand pane, select **Research plan**. Enter the hypothesis,
   method/controls, expected outcome, and decision criteria. Select **Save
   research plan** before running the experiment.
3. Each save appends a new record. Older plans remain inspectable in the result
   list. Plans are labeled `MODEL_ASSUMPTION`; they are not observations.

## Run and inspect

4. Select **Open Simulation**. Choose a supported model, exposure, duration,
   ensemble size, seed and assumed rates. Use the NumPy backend for the local CPU
   route. **Run paired experiment** saves both exposure and zero-exposure control
   trajectories, the protocol configuration, model/source hashes and numerical
   checks. New runs attach to the experiment active when submission began.
5. Open **Analysis** to inspect the selected endpoint, trajectory, control, final
   distribution and parameter associations. To restore a particular saved run,
   select it in **Projects**. The biological validity of an assumed model is not
   established by numerical agreement.
6. For a second scenario, change the intended input and run again. **Compare**
   explicitly selects two saved simulations and shows final-state medians,
   5th–95th ensemble percentiles, and the difference of medians. Comparisons
   require the same model/version, time span, quantity semantics and units.
   These summaries describe simulations; percentiles are not confidence
   intervals. Check the saved protocols for other changed assumptions.
7. To work in other analysis software, select a simulation in Projects, enter a
   full new `.csv` path and select **Export selected simulation CSV**. The CSV
   preserves run/experiment IDs, units, times, exposure/control scenarios,
   quantiles and the `SIMULATED` label. An existing file is never overwritten.

## Interpretation and durable handoff

8. In Projects → **Conclusion**, enter an interpretation and its limitations,
   choose a scoped decision, and explicitly check the saved results used as
   evidence. Select **Save researcher conclusion**.
9. The conclusion is a human interpretation labeled `INFERRED`. It references
   the latest saved plan and the exact hashes of selected results in the same
   experiment. Tampered, missing or foreign results are rejected. If selected
   results predate the plan, the record says `retrospective`; the application
   does not turn a retrospective plan into a preregistration. A changed research
   question requires a new saved plan before another conclusion.
10. Enter a full new `.vlab-study` path and export the study. The package carries
    its question, saved plan(s), result protocols/data, conclusion(s), explicit
    citations and artifact hashes. Import into a separate workspace and inspect
    the same records. Import checks citation relationships as well as bytes and
    rejects incomplete or mismatched evidence links before creating the study.

A study package is unsigned. Hashes establish consistency, not the author's
identity, original execution, or scientific correctness. Packages containing the
new research-record observation type require an updated VirtualLab reader.

## Recorded instrument data

Committed sensor sessions now include the artifact path, digest and acquisition
time required to attach them to an experiment. They remain associated with the
experiment selected at recording start. Raw JSONL/camera artifacts can be
hash-inspected and cited without parsing them as simulation JSON. Their bytes
travel with exported studies. This is an integrity workflow; it does not replace
instrument calibration or scientific analysis. Physical devices were not used in
the automated verification. Closing the app commits an active recording before
shutting down; a save failure keeps the window open.

## Persistence and optional services

Application data uses a stable platform directory, so launching from another
working directory does not create a separate research workspace:

- macOS: `~/Library/Application Support/VirtualLab/cockpit`
- Linux: `$XDG_DATA_HOME/VirtualLab/cockpit`, defaulting to
  `~/.local/share/VirtualLab/cockpit`
- Windows: `%LOCALAPPDATA%/VirtualLab/cockpit`

Use an absolute `VIRTUALLAB_DATA_DIR` to select an isolated workspace. The
experiment database, runtime ledger, run artifacts, instrument captures and
measurement sessions all use this location. Existing files in older
working-directory `.virtuallab/` or `data/instruments/` locations are retained;
they are not silently merged or removed. Keep these legacy files when retaining
older audit records, and use study export/import for portable experiment data.

Opening **Instruments** explicitly starts its listener. It is not started for
the manual simulation workflow. AI can be added with `pip install -e '.[ai]'`
and enabled using **AI assistance (optional) → Enable optional AI assistance**.
Missing AI packages or credentials do not prevent the manual workflow.

## Verification

The executable GUI regression creates a project, saves a plan, runs two
simulations, compares them, exports CSV, saves a cited conclusion, exports a
study, restarts from a different directory, and imports into a new workspace.
It blocks all `virtual_lab.ai`, Google GenAI, Google ADK and MLX-LM imports:

```sh
python -m pip install -e '.[cockpit,dev]'
python -m pytest tests/gui/test_manual_research_flow.py tests/projects -q
```

Additional checks reject foreign/tampered evidence, broken citations in an
otherwise hash-consistent package, incompatible comparisons and output-file
overwrite. Linux CI includes an installation without either Google AI SDK.
