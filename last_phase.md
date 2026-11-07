# MDRPA --- Final Development & Release Plan

> **Document status:** Temporary working roadmap\
> **File:** `last_phase.md`\
> **Repository:** `AASH010/MEDA-Data-Research-Period-Analyzer-MDRPA`\
> **Target branch:** `main`\
> **Purpose:** Track the remaining work required to complete, validate,
> package, and release the MEDA Data Research & Period Analyzer (MDRPA).

------------------------------------------------------------------------

## 1. Purpose and Scope

This document records the agreed remaining development plan for MDRPA.
It is a temporary project-tracking document and will remain in the
repository until the project is fully completed.

When all development, validation, packaging, and release activities are
finished, the project documentation must be reviewed and consolidated.
At that point, this temporary file may be archived or removed after its
relevant information has been incorporated into the permanent
documentation.

This roadmap does not replace the project architecture, scientific
methodology, development guide, or user guide.

## 2. Current Project Status

### 2.1 Confirmed Progress

The project has progressed beyond isolated scientific analyzers and now
has a connected analysis workflow and desktop application foundation.

The following components have been implemented or substantially
implemented and are subject to final review:

-   Scientific analysis components:
    -   File discovery.
    -   XML metadata parsing.
    -   Coverage analysis.
    -   Quality analysis.
    -   Synchronization analysis.
    -   Period ranking.
-   Run management and per-run organization.
-   Pipeline orchestration and stage-result tracking.
-   Background execution through the application worker/controller flow.
-   Cooperative cancellation support.
-   Core GUI structure, navigation, input selection, analysis
    configuration, execution controls, and dashboard views.
-   Regression and pipeline test coverage.

### 2.2 Latest Reported Test Result

The latest test result reported by the project owner is:

``` text
988 passed, 4 skipped in 54.43s
```

This is a strong regression-test result. It does not, by itself,
establish scientific validity, complete GUI functionality, successful CI
execution, or release readiness.

The four skipped tests must be identified and their skip reasons
reviewed before final acceptance.

### 2.3 Known Completion Gaps

The following areas require further implementation, verification, or
explicit acceptance:

-   Reports page and report export workflow.
-   Overview page and other remaining GUI placeholders.
-   Help, About, Credits, and first-launch tutorial experience.
-   End-to-end workflow verification.
-   Scientific validation using representative original MEDA data.
-   Final regression, GUI, platform, and CI verification.
-   Windows packaging and clean-machine installation testing.
-   Documentation synchronization and release preparation.

### 2.4 Phase Status Assessment

The phase labels below are a working assessment, not a claim that every
phase has passed formal acceptance.

  -----------------------------------------------------------------------
  Phase                   Area                    Current assessment
  ----------------------- ----------------------- -----------------------
  P0                      Project governance and  Implemented in part;
                          foundations             documentation alignment
                                                  remains

  P1                      Backend and analyzer    Core audit performed;
                          audit                   scientific validation
                                                  remains

  P2                      Run Manager             Core implementation
                                                  present; final
                                                  verification remains

  P3                      Pipeline integration    Core implementation
                                                  present; final
                                                  verification remains

  P4                      Execution engine        Core implementation
                                                  present; final
                                                  verification remains

  P5                      GUI foundation          Core implementation
                                                  present

  P6                      GUI modules and user    Partially complete
                          workflows               

  P7                      Testing and validation  Strong test progress;
                                                  scientific and release
                                                  validation remain

  P8                      Packaging and release   Final implementation
                                                  remains
  -----------------------------------------------------------------------

A phase must not be marked complete solely because files or classes
exist. Completion requires implementation, tests or other appropriate
verification, review, and project-owner acceptance.

------------------------------------------------------------------------

## 3. Remaining Development Roadmap

The work must proceed in the order below unless a blocking dependency or
a newly discovered critical defect requires reprioritization.

## Phase 1 --- Complete the GUI Modules

**Objective:** Turn the existing GUI foundation into a complete and
coherent user-facing application.

### P6.1 --- Reports and Export

Implement and integrate the Reports page.

Required work:

-   Display reports belonging to each analysis Run.
-   Preserve the relationship between every report and its Run ID.
-   Provide suitable viewing for supported report formats, including
    JSON and CSV.
-   Display report metadata, warnings, limitations, and relevant
    execution status.
-   Provide appropriate report export functionality.
-   Prevent reports from different Runs from being mixed.
-   Handle missing, incomplete, or unreadable report artifacts clearly.

**Acceptance criteria:**

-   Users can locate and open reports for a selected Run.
-   Reports are traceable to their source Run and configuration.
-   Supported exports are written to the intended destination.
-   Missing or invalid reports are not presented as successful results.
-   Relevant automated tests pass.

### P6.2 --- Overview Dashboard

Replace the current Overview placeholder with a useful application
overview.

Expected content may include:

-   Application identity and version.
-   Recent Runs and their statuses.
-   High-level analysis summaries.
-   Useful navigation to input, analysis, dashboard, and reports
    workflows.
-   Clear empty-state behavior when no Runs exist.

**Acceptance criteria:**

-   The Overview page displays real application state rather than
    placeholder text.
-   Empty, loading, completed, failed, and unavailable states are
    handled clearly.
-   Displayed information is consistent with Run Manager records.

### P6.3 --- Help, About, and Credits

Implement the application information and help experience.

Required work:

-   Help content describing the main workflow.
-   About dialog or page.
-   Application version information.
-   Credits and relevant acknowledgements.
-   Scientific and software references where appropriate.
-   Clear access to help from the application interface.

**Acceptance criteria:**

-   Help and About are accessible from the application.
-   Version and attribution information is accurate.
-   Scientific references are not fabricated or presented without
    verification.

### P6.4 --- First-Launch Tutorial

Implement an introductory experience for first-time users.

Required work:

-   Explain the main workflow: select data, validate input, configure
    analysis, execute, and inspect results.
-   Provide a way to dismiss or complete the tutorial.
-   Persist the completion state using the application settings
    mechanism.
-   Allow users to reopen the tutorial or help content later.
-   Avoid interrupting normal use after the tutorial has been completed.

**Acceptance criteria:**

-   First-launch behavior is predictable.
-   Tutorial completion is persisted.
-   Users can access guidance again.

### P6.5 --- GUI Integration Review

Review the GUI as one connected application.

Review:

-   Navigation and page registration.
-   Input validation and configuration handoff.
-   Start and cancellation controls.
-   Progress and stage status updates.
-   Error and warning presentation.
-   Dashboard refresh after execution.
-   Report navigation and Run selection.
-   Application shutdown while a worker is active.
-   Empty and exceptional states.

**Acceptance criteria:**

-   No placeholder page remains in the intended primary user workflow.
-   GUI state accurately reflects backend and Run Manager state.
-   No incomplete output is presented as a finished result.
-   GUI tests and relevant integration tests pass.

------------------------------------------------------------------------

## Phase 2 --- End-to-End Integration Verification

**Objective:** Verify the complete application workflow from input
selection to persisted results.

Required scenarios:

1.  Select a valid MEDA dataset.
2.  Validate the selected input directory.
3.  Configure an analysis period and supported options.
4.  Create a new Run with a unique identity.
5.  Prepare isolated Run storage.
6.  Execute all required pipeline stages.
7.  Verify stage order and dependencies.
8.  Verify required output artifacts.
9.  Display the completed Run in the GUI.
10. Open the Run's reports and dashboards.
11. Close and reopen the application.
12. Verify that previous Run records and outputs remain available.

Failure and recovery scenarios:

-   Invalid or empty input directory.
-   Missing required files.
-   Malformed or unsupported input files.
-   XML parsing failure.
-   Analyzer failure.
-   Missing or invalid stage output.
-   Output writing failure.
-   User-requested cancellation.
-   Application shutdown during active execution.
-   Run directory collision.
-   Reopening the application after an interrupted Run.
-   Multiple Runs with different configurations.
-   Preservation of previously completed Runs after a later Run fails.

**Acceptance criteria:**

-   A complete valid workflow succeeds.
-   Each failure is recorded against the correct Run and stage.
-   Dependent stages do not appear successful when their prerequisites
    fail.
-   Cancellation and shutdown behavior are safe and consistent.
-   Run outputs remain isolated and previous results are preserved.

------------------------------------------------------------------------

## Phase 3 --- Scientific Validation

**Objective:** Establish that the software's calculations and reports
behave as documented when processing representative original MEDA data.

This phase is distinct from ordinary software testing. Passing unit
tests does not independently establish scientific validity.

### P7.1 --- Validation Dataset

-   Select representative original MEDA datasets.
-   Record source, provenance, applicable product types, and relevant
    metadata.
-   Preserve a controlled validation fixture or documented retrieval
    procedure.
-   Ensure test data licensing and redistribution conditions are
    respected.

### P7.2 --- Input and Time Interpretation

-   Verify CSV and XML field mapping.
-   Verify header normalization and missing-field handling.
-   Review timestamp parsing and supported time axes.
-   Verify time-zone and time-unit assumptions where applicable.
-   Verify handling of malformed, duplicated, missing, and out-of-order
    records.

### P7.3 --- Coverage Analysis

-   Review coverage definitions.
-   Verify period boundaries and interval handling.
-   Verify gap detection and duration calculations.
-   Verify partial-period behavior.
-   Verify treatment of missing or invalid observations.

### P7.4 --- Quality Analysis

-   Verify the meaning and source of each quality metric.
-   Verify documented bounds and missing-value behavior.
-   Verify summary calculations and period filtering.
-   Ensure technical data checks are not described as scientific
    validation unless supported by documented criteria.

### P7.5 --- Synchronization Analysis

-   Verify product-pair matching rules.
-   Verify timestamp tolerance behavior.
-   Verify duplicate handling and unmatched records.
-   Verify counts and summaries against independently checked examples.

### P7.6 --- Period Ranking

-   Document ranking metrics, weights, normalization, and tie behavior.
-   Verify missing-metric handling.
-   Verify boundary conditions and deterministic output.
-   Confirm that ranking labels do not imply stronger scientific
    conclusions than the methodology supports.

### P7.7 --- Scientific Regression Baselines

-   Create expected-result fixtures from independently checked examples.
-   Compare generated reports against the expected results.
-   Record acceptable numerical tolerances and their rationale.
-   Ensure changes to scientific formulas require explicit review and
    regression updates.

**Acceptance criteria:**

-   Each metric has a documented definition and traceable input.
-   Representative real-data cases have independently checked expected
    results.
-   Ranking behavior is reproducible and documented.
-   Known limitations are visible to users.
-   No scientific formula or ranking weight is changed silently.

------------------------------------------------------------------------

## Phase 4 --- Final Testing and Regression

**Objective:** Establish technical stability across supported
environments and workflows.

Required work:

-   Run the complete test suite.
-   Identify and review all skipped tests.
-   Review test coverage for critical branches and failure modes.
-   Run unit, integration, pipeline, Run isolation, and GUI tests.
-   Verify supported Python versions, including Python 3.10 and 3.11
    where applicable.
-   Verify GitHub Actions CI workflows and record their actual results.
-   Test on supported Windows environments.
-   Exercise larger representative datasets and review runtime and
    memory behavior.
-   Review logging, exception handling, and user-facing error messages.
-   Verify that source datasets are not unintentionally modified.
-   Verify that user data remains outside the application installation
    directory.
-   Verify that existing Runs remain available after failures and
    upgrades.

**Acceptance criteria:**

-   All required tests pass.
-   Every skipped test has a documented and accepted reason.
-   Required CI checks pass on the intended release commit.
-   No unresolved critical or high-severity defect blocks release.
-   Performance is acceptable for the documented supported dataset
    sizes.

------------------------------------------------------------------------

## Phase 5 --- Windows Packaging and Release Preparation

**Objective:** Deliver MDRPA as a usable Windows application that does
not require users to create the development environment manually.

### P8.1 --- Entry Point and Build Configuration

-   Confirm the official application entry point.
-   Confirm runtime resource paths.
-   Identify required hidden imports and bundled resources.
-   Define application name, version, and icon.
-   Create and review the PyInstaller specification.
-   Keep development-only dependencies out of the runtime package where
    practical.

### P8.2 --- Executable Build

-   Build the Windows executable.
-   Include required Qt plugins, resources, and dependencies.
-   Verify application startup and shutdown.
-   Verify configuration and user-data paths.
-   Verify that logs and Run outputs are written to appropriate
    user-writable locations.

### P8.3 --- Clean-Machine Testing

Test on a clean supported Windows environment without the development
Python environment.

Verify:

-   Installation or extraction.
-   Application startup.
-   Input selection.
-   A complete analysis Run.
-   Dashboard and report viewing.
-   Export.
-   Persistence after restart.
-   Error handling.
-   Uninstallation or removal behavior, as applicable.

### P8.4 --- Distribution

-   Decide whether to distribute a portable executable, installer, or
    both.
-   Prepare versioned release artifacts.
-   Prepare release notes.
-   Record supported operating systems and known limitations.
-   Verify checksums or other integrity information where appropriate.

**Acceptance criteria:**

-   The packaged application starts on a clean supported Windows
    environment.
-   A representative complete analysis succeeds.
-   User data is stored in the intended location and survives
    application restarts.
-   Release artifacts and instructions are reproducible.

------------------------------------------------------------------------

## Phase 6 --- Final Acceptance and Documentation Consolidation

**Objective:** Confirm that the released product, its documentation, and
its declared capabilities agree.

Required work:

-   Update `README.md`.
-   Update `docs/user_guide.md`.
-   Update `docs/architecture.md`.
-   Update `docs/development_guide.md`.
-   Update scientific methodology and analyzer documentation where
    needed.
-   Document installation, startup, data selection, analysis, reports,
    and troubleshooting.
-   Document scientific assumptions, limitations, and supported input
    formats.
-   Review licensing, third-party notices, and acknowledgements.
-   Review versioning and release notes.
-   Perform a final repository-wide file and placeholder audit.
-   Run the final release test suite against the release candidate.
-   Record final acceptance.

**Acceptance criteria:**

-   Documentation matches the released application.
-   No planned feature is described as implemented unless verified.
-   No implemented core feature is omitted from user documentation.
-   Known limitations are explicit.
-   The release candidate passes its required acceptance checks.

------------------------------------------------------------------------

## 4. File Review and Implementation Order

The implementation and review sequence should follow dependencies and
avoid unnecessary changes to already stable scientific components.

  ------------------------------------------------------------------------
  Order                   File group               Review or
                                                   implementation focus
  ----------------------- ------------------------ -----------------------
  1                       `gui/main_window/`       Page registration,
                                                   navigation, placeholder
                                                   audit, application
                                                   lifecycle

  2                       `gui/reports/`           Report listing,
                                                   viewing, Run
                                                   traceability, export

  3                       `gui/tutorial/`          First-launch tutorial
                                                   and persisted
                                                   completion state

  4                       `gui/dialogs/`           Help, About, Credits

  5                       `gui/dashboard/`         Dashboard integration
                                                   and state consistency

  6                       `application/`           Startup, configuration,
                                                   controller ownership,
                                                   application lifecycle

  7                       `backend/run_manager/`   Run isolation,
                                                   metadata, persistence,
                                                   recovery

  8                       `backend/pipeline/` and  Stage orchestration,
                          `backend/workers/`       cancellation, errors,
                                                   worker lifecycle

  9                       `backend/analyzers/`     Scientific validation
                                                   against representative
                                                   MEDA data

  10                      `tests/`                 Regression,
                                                   integration, GUI, and
                                                   scientific validation
                                                   tests

  11                      `packaging/`             PyInstaller
                                                   configuration and
                                                   release build

  12                      `docs/`                  Documentation
                                                   synchronization and
                                                   final user/developer
                                                   guidance
  ------------------------------------------------------------------------

The file list is a review sequence, not a claim that every listed
directory already exists. Before editing, inspect the current repository
tree and use the actual paths present on the target branch.

------------------------------------------------------------------------

## 5. Engineering Rules for the Remaining Work

The following rules apply throughout the remaining development:

1.  Do not rewrite an analyzer that has passed review without a
    documented defect or requirement.
2.  Do not change scientific formulas, ranking weights, thresholds, or
    interpretation rules without explicit review and approval.
3.  Preserve each Run's identity, configuration, metadata, logs, and
    outputs.
4.  Do not treat the existence of a GUI page as proof that its
    functionality is complete.
5.  Do not treat passing automated tests as proof of scientific
    validity.
6.  Do not begin final packaging until GUI integration, end-to-end
    verification, and required regression tests are stable.
7.  Mark a phase complete only after its acceptance criteria are met and
    reviewed.
8.  Inspect the latest target-branch file before proposing a full-file
    replacement.
9.  Avoid overwriting uncommitted user changes; clarify differences when
    the local working copy may be ahead of the remote branch.
10. Do not create commits, push changes, or modify the remote repository
    without explicit authorization.
11. Keep changes focused and review one file or one tightly related
    group at a time.
12. Update tests and relevant documentation whenever behavior or
    supported interfaces change.
13. Never fabricate missing scientific values or silently convert failed
    stages into successful results.
14. Keep user-generated data separate from source code and the installed
    application.
15. Record newly discovered blockers and update this roadmap when scope
    or dependencies materially change.

------------------------------------------------------------------------

## 6. Definition of Done --- MDRPA

MDRPA may be declared complete only when all applicable conditions below
are satisfied:

-   [ ] All core GUI pages and workflows are implemented.
-   [ ] No placeholder remains in the intended primary user workflow.
-   [ ] Users can select and validate MEDA input data.
-   [ ] Users can configure and execute a complete analysis.
-   [ ] All required pipeline stages behave correctly.
-   [ ] Cancellation, failure, and shutdown behavior are verified.
-   [ ] Runs are uniquely identified and isolated.
-   [ ] Previous Run records and artifacts remain accessible.
-   [ ] Reports can be viewed and exported.
-   [ ] Scientific calculations are validated against representative
    MEDA data.
-   [ ] Ranking methodology and limitations are documented.
-   [ ] All required tests pass.
-   [ ] Skipped tests are reviewed and justified.
-   [ ] Required CI checks pass on the release candidate.
-   [ ] Windows packaging succeeds.
-   [ ] The packaged application passes clean-machine testing.
-   [ ] User and developer documentation matches the final product.
-   [ ] Licensing, dependencies, credits, and release notes are
    reviewed.
-   [ ] Final project-owner acceptance is recorded.

------------------------------------------------------------------------

## 7. Immediate Next Task

### CODEP-01 --- GUI Completion Audit

**Status:** Proposed next task\
**Phase:** P6 --- GUI Modules\
**Scope:** Audit only; no implementation changes during the initial
audit.

Tasks:

1.  Inspect the current GUI repository tree.
2.  List every registered GUI page and dialog.
3.  Classify each component as complete, partial, placeholder, or not
    found.
4.  Inspect the current Reports implementation and related backend
    report artifacts.
5.  Inspect tutorial, help, About, and Credits components.
6.  Identify reusable components and existing tests.
7.  Record dependencies and blockers.
8.  Produce a file-by-file implementation sequence for the remaining GUI
    work.

**Deliverable:** A verified GUI completion audit and a set of focused
implementation tasks.

**Exit condition:** The GUI scope is clear, existing functionality is
accounted for, and the next implementation task can be started without
guessing or duplicating existing work.

------------------------------------------------------------------------

## 8. Project Completion Principle

The project is complete when a user can install and launch MDRPA, select
MEDA data, run a complete analysis, inspect and export traceable
results, and return to previous Runs --- with documented scientific
methods, verified behavior, and no need to manually configure the
development environment.

**The goal is not merely a program that opens or a test suite that
passes. The goal is a reliable, reproducible, scientifically
transparent, and distributable MEDA analysis tool.**

------------------------------------------------------------------------

## 9. Temporary Roadmap Maintenance

This file is intentionally temporary.

-   Keep it updated as phases are completed or reprioritized.
-   Record meaningful decisions, blockers, and acceptance outcomes.
-   Do not use it as a substitute for permanent technical documentation.
-   At final project completion, transfer the lasting information into
    the appropriate permanent documentation.
-   Remove or archive `last_phase.md` only after documentation
    consolidation and final acceptance.
