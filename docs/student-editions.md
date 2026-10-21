# Student editions: three profiles, one scientific engine

Design proposal, October 20, 2026. These profiles are not implemented by this document. The current desktop usability fixes can ship independently. The existing onboarding draft needs further review before classroom use.

Use one application with a visible learning-profile selector and a shared `.vlab-study` format. Avoid three forks of the scientific models. Students can change profiles without converting or rewriting their saved research. A teacher can prepare a versioned assignment; the student owns a separate study workspace.

| | High school: Guided Discovery | Undergraduate: Lab Course | Graduate: Research Starter |
|---|---|---|---|
| Main journey | Question → Predict → Experiment → Explain → Submit | Plan → Design → Run → Compare → Check → Conclude → Export | Guided research checklist with access to the full cockpit |
| Starting material | Teacher supplies a question and a clearly labeled model | Teacher supplies the problem and model family | Student chooses question, model, and evidence |
| Controls shown initially | One named independent variable, units, two scenarios, paired control | Exposure, duration, sample count, seed, assumptions, uncertainty | Full design, numerical scope, calibration and provenance |
| Advanced settings | Collapsed explanation of fixed assumptions | Expandable parameter editor and solver settings | Available throughout, with contextual explanations |
| Results | One graph at a time; exposure/control labels; endpoint difference | Trajectories, distributions, units, parameter associations | Full plots, comparison, numerical certificates and evidence links |
| Interpretation | Student writes claim, supporting observations, and limitations | Student links results to a prospective plan and discusses uncertainty | Student writes a scoped conclusion and proposes a falsifiable next study |
| AI | Off by default; not needed | Off by default; optional instructor-enabled critique | Optional critique with source checking and explicit scope |
| Submission | Native study plus a readable summary | Native study and CSVs | Full portable study and CSVs, with provenance review |

## Shared interface

Start with **Open assignment**, **Start my study**, or **Continue study**. Show a persistent progress indicator and one primary next action. Explain technical terms next to their controls rather than requiring a manual first. Keep Back and Save/Continue visible. Show the current study and model in every stage.

A student should never need to visit the instrument, protein structure, local-model, or cloud-credential screens to complete the introductory lesson. Those tools remain available in the full researcher view. Physical instrumentation remains explicitly deferred until a working instrument and its validation are available.

Results review has two views: **What changed?** presents the graph and endpoint differences; **How reliable is this calculation?** explains the numerical reference, checked subset, tolerances and assumptions. Always distinguish parameter draws from biological replicates and numerical agreement from biological validation. A passing certificate must not appear as a green “biology proven” badge.

## First lesson for all three groups

Use the existing generic gene-expression model and paired zero-exposure controls. Save the learner's prediction before running. Compare 1 and 5 µM exposures at 24 hours with the same seed and parameter draws. Display 128 draws and assumed spread 0.10 explicitly; introductory profiles can keep them fixed with an explanation. These are normalized model outputs, not a particular gene, tissue, organism or biological measurement.

1. Save a question and prediction in the learner's own words.
2. Review the model and fixed assumptions; choose the two exposures.
3. Show a confirmation card with actual numeric inputs before each run. This prevents a scenario label from being mistaken for an exposure value.
4. Run and compare the intended scenarios. Keep mistaken runs in history with an explanatory note; let the student select which runs support the comparison.
5. Explain what the numerical check covers and what it leaves unchecked.
6. Write an interpretation and at least one limitation; cite the selected results.
7. Export, import into a clean workspace, and reopen the graph before submitting.

High-school students receive graph-reading prompts. Undergraduates also justify controls and discuss uncertainty. Graduate students additionally test robustness across seeds or assumed parameters and propose what physical evidence would be needed next. Students should not be graded on obtaining a preferred hypothesis outcome.

## Keep practice separate from assessment

The guided example can demonstrate an action in a dedicated practice study. It must not write a canned hypothesis or conclusion into an existing research study, mark automated text as student-authored, or automatically complete assessed work. Require the learner to supply their own prediction and interpretation for a submission. Label demonstration studies and generated examples explicitly.

An assignment package should pin the model version, starting assumptions, allowed controls, task text and rubric. Open it by copying into a new learner workspace; never edit the teacher's original package. Preserve raw artifacts and historical provenance. A proposed assignment extension needs its own versioned schema and backward-compatibility tests; existing study packages should continue to import unchanged.

## Build order and acceptance checks

1. **Shared student shell:** profile picker, the stage navigation, a dedicated practice workspace, and access to the full researcher view. Complete the first lesson offline from a clean installation.
2. **High-school prompts:** plain-language labels, one-variable controls, confirmation cards, graph questions, and a learner-authored reflection. Complete at 800×600 with every control visible or reachable by scrolling and keyboard.
3. **Undergraduate tools:** editable protocols, uncertainty explanation, evidence-linked conclusions, CSV export and an assignment rubric. Verify citation controls while adding three or more runs.
4. **Graduate guidance:** full controls with a progress checklist, evidence provenance, calibration prerequisites and reproducibility exercises.
5. **Teacher and submission tools:** assignment packaging, accessible readable summaries and human review. Evaluate an exported submission in a separate workspace and retain the original bytes.

Before classroom release, resolve the security and provenance blockers from the independent audit, verify old study imports, test each profile with representative learners, and run native keyboard/screen-reader checks on supported platforms. The current layout tests and usability fixes do not certify those separate blockers as resolved.
