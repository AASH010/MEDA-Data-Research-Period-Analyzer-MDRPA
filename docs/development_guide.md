# Development Guide

## MEDA Data Research & Period Analyzer (MDRPA)

## 1. Purpose

This document defines the mandatory development workflow, engineering rules, review procedures, and acceptance criteria for the **MEDA Data Research & Period Analyzer (MDRPA)** project.

Its purpose is to ensure that development remains controlled, traceable, reproducible, and scientifically responsible.

All project development activities must follow this guide.

## 2. Project Identity and Source of Truth

### 2.1 Official Project Identity

- **Project Name:** MEDA Data Research & Period Analyzer
- **Abbreviation:** MDRPA
- **Official Repository:** `https://github.com/AASH010/MEDA-Data-Research-Period-Analyzer-MDRPA`
- **Target Branch:** `main`

The official project name and abbreviation must remain consistent throughout the repository and its documentation.

### 2.2 Source of Truth

- The official GitHub repository is the reference for the committed project state.
- The target branch is `main`, unless an explicitly approved task specifies otherwise.
- The latest commit must be identified before repository-related work begins.
- Local files must not be assumed to match GitHub.
- Existing files, interfaces, and documentation must be inspected before creating replacements or new modules.
- No file should be created, deleted, renamed, or substantially modified without an explicitly scoped task and approval.

## 3. Mandatory Task Lifecycle

Every development task must follow these stages in order:

1. **Define** — Specify the objective, scope, expected outputs, and exclusions.
2. **Inspect** — Examine relevant files, interfaces, dependencies, existing documentation, and current repository state.
3. **Assess** — Report findings, risks, constraints, and the proposed approach.
4. **Approve** — Obtain explicit user approval before implementation or preparation of an authorized replacement.
5. **Implement / Prepare** — Prepare only the approved changes.
6. **Test** — Execute relevant tests and report exact commands and results.
7. **Review** — Examine the changes, side effects, and consistency with project requirements.
8. **Close** — Record the outcome, remaining issues, and next authorized task.

No stage may be skipped.

If an unexpected issue changes the task scope, work must stop until the issue has been inspected and the revised scope approved.

For documentation-only tasks, testing may consist of consistency checks and review rather than software execution. The reason must be stated in the task report.

## 4. Task Scope and Change Control

Every task must define:

- Task ID.
- Project phase.
- Objective.
- Files and components in scope.
- Expected changes.
- Explicit exclusions.
- Required tests or review procedures.
- Acceptance criteria.

Changes must remain within the approved scope.

Unrelated cleanup, refactoring, renaming, dependency changes, and architectural modifications are not permitted unless separately approved.

A discovered improvement must be recorded as a proposed follow-up task rather than silently added to the current task.

### 4.1 Controlled File-by-File Workflow

When a phase requires work on multiple existing files:

- Follow the approved file order.
- Complete one file at a time unless a related group is explicitly approved.
- Inspect the current file before preparing its replacement.
- For populated files, provide a complete revised version.
- For empty files, provide complete ready-to-use content.
- Wait for the user's review, upload, and confirmation before moving to the next file.
- Do not assume that a file has been uploaded merely because its replacement was provided.

## 5. File and Documentation Rules

- Inspect existing files before creating new ones.
- Reuse the existing project structure whenever appropriate.
- Avoid duplicate modules and documentation with overlapping responsibilities.
- Preserve established naming conventions unless a change is approved.
- Keep documentation consistent with the actual implementation.
- Do not document planned functionality as implemented functionality.
- Do not delete or rename existing files without an explicit decision.
- Each documentation file must have a clearly defined responsibility.
- Preserve the official project name and abbreviation.
- Update documentation when an approved implementation change affects documented behavior.

Documentation must distinguish between implemented, tested, accepted, planned, and unavailable functionality.

## 6. Architecture and Separation of Responsibilities

The project maintains separation between:

- Scientific analysis modules.
- Backend orchestration and integration.
- Run management and execution services.
- Background workers.
- Graphical user interface.
- Reporting and export functionality.
- Validation and testing.

The GUI must not independently reimplement scientific analysis logic.

Backend modules must not depend on GUI rendering components.

Integration changes must preserve the documented scientific behavior of existing analyzers unless a separate scientific change has been reviewed and approved.

### 6.1 Backend and GUI Separation

- Scientific calculations belong in the backend.
- GUI modules are responsible for user interaction and presentation.
- Communication between the GUI and backend must use defined interfaces.
- Long-running analysis operations must not block the GUI thread.
- GUI changes must not silently alter scientific calculations.

## 7. Scientific Integrity Rules

Scientific interpretation must be based on authoritative documentation and verified implementation behavior.

The following distinctions must be preserved:

- File availability is not data completeness.
- Data completeness is not measurement quality.
- Measurement quality is not scientific validity.
- Metadata warnings are not automatically measurement quality issues.
- Numeric range checks are not comprehensive scientific validation.
- Synchronization match rates are diagnostics, not quality scores.
- Temporal overlap does not establish identical sampling.
- Candidate period rankings are exploratory comparisons, not scientific certification.

Quality flags must not be interpreted without their official definitions.

Mission-specific timestamps must not be converted to another time system without an authoritative reference.

The following must not be assumed:

- Binary quality flags automatically mean `1 = good` and `0 = bad`.
- A numeric value is scientifically valid simply because it is parseable.
- A matching timestamp proves scientific equivalence between products.
- MEDA observations provide continuous spatial coverage across every geographical grid cell.
- A higher ranking score establishes scientific suitability.

No scientific assumptions, thresholds, weights, or ranking rules may be changed without explicit review and approval.

## 8. Run Isolation and Data Protection

Each analysis execution must have an independent identity and isolated storage.

- Every run must receive a unique Run ID.
- Repeated analyses of the same Sol range must create distinct runs.
- Input files, configurations, metadata, logs, and outputs must not be mixed between runs.
- Existing run data must not be overwritten unintentionally.
- User-generated data must remain separate from application source files.
- Failed or interrupted runs must retain an accurate status.
- Run paths and identifiers must be validated before execution.
- A run must not silently reuse another run's output directory.

Run isolation must be enforced by the Run Manager and verified through appropriate tests.

## 9. Testing Requirements

Code implementation alone does not establish task completion.

Tests must be appropriate to the scope and may include:

- Unit tests.
- Integration tests.
- Regression tests.
- Input and output validation.
- Error-handling tests.
- Data isolation tests.
- Scientific consistency checks.
- GUI behavior tests.
- Background execution tests.
- Packaging tests.

Every test report must identify:

- Exact command or procedure.
- Test environment, where relevant.
- Expected result.
- Actual result.
- Pass or failure status.
- Known limitations.

A test must not be reported as passed if it was not executed.

Unavailable tests and unverified behavior must be explicitly identified.

### 9.1 Scientific Test Requirements

Scientific tests must use representative data and documented expectations wherever possible.

A technically successful execution does not automatically establish scientific correctness.

Test results must distinguish software behavior from scientific interpretation.

## 10. Task Status Definitions

Tasks must use the following controlled status labels:

| Status | Meaning |
|---|---|
| PLANNED | Defined but not started |
| INSPECTING | Existing state is being examined |
| REVIEW | Findings and proposed changes are awaiting review |
| APPROVED | Scope and proposed approach are authorized |
| IMPLEMENTING | Approved changes are being prepared |
| TESTING | Required tests are being executed |
| REVIEWING | Changes and test evidence are being reviewed |
| PASSED | Required tests and technical checks passed |
| ACCEPTED | Final outcome explicitly accepted |
| BLOCKED | Progress cannot continue because of an unresolved issue |

A task must not be marked `ACCEPTED` merely because implementation is complete or tests have passed.

Acceptance requires explicit user confirmation.

## 11. Git and Repository Responsibilities

- The official target branch is `main`.
- The latest repository commit must be checked before repository-related tasks.
- Changes must be prepared against the inspected repository state.
- The user performs local file modifications and Git operations.
- The assistant may inspect repository content and provide complete replacement files or proposed changes.
- The assistant must not claim that local files were modified, commits were created, or changes were pushed unless those actions were actually performed and verified.
- No unapproved direct repository changes are permitted.
- The final review must identify the exact files and changes involved.
- The user confirms when changes have been uploaded to the official repository.

### 11.1 Repository Change Verification

After the user reports that a change has been uploaded:

1. Confirm the intended file and branch.
2. Inspect the published version when repository access is available.
3. Check that the uploaded content corresponds to the approved version.
4. Record any differences or unresolved issues.
5. Obtain acceptance before moving to the next authorized task.

## 12. Required Task Report

Every completed or blocked task must have a concise report containing:

- Task ID.
- Project phase.
- Objective.
- Repository and target branch.
- Inspected commit, when applicable.
- Files inspected.
- Files changed or proposed.
- Changes made or proposed.
- Tests or review procedures executed.
- Test results.
- Known limitations.
- Remaining issues.
- Final status.
- Next authorized task.

The report must distinguish between changes prepared for the user and changes verified as uploaded to GitHub.

## 13. Phase Transition Rules

Project phases must follow the approved development roadmap:

- P0 — Project Governance.
- P1 — Backend Audit.
- P2 — Run Manager.
- P3 — Pipeline Integration.
- P4 — Execution Engine.
- P5 — GUI Foundation.
- P6 — GUI Modules.
- P7 — Testing and Validation.
- P8 — Packaging and Release.

A phase may advance only when:

1. Its required tasks have been completed.
2. Required tests and reviews have passed.
3. Outstanding limitations have been documented.
4. Required documentation has been updated.
5. The user has explicitly accepted the phase outcome.

No later phase may begin merely because the previous phase's implementation work appears finished.

## 14. Change History and Traceability

Development decisions should be traceable to their approved tasks.

Significant architectural, scientific, interface, and workflow decisions must be documented in the appropriate project document.

Documentation must distinguish between:

- Approved decisions.
- Implemented functionality.
- Tested functionality.
- Accepted functionality.
- Planned functionality.
- Known limitations.

When a decision changes, the relevant documentation must be updated through an approved task.

## 15. Governing Principle

**No assumptions, no unapproved changes, no skipped tests, and no phase transitions without acceptance.**

The MEDA Data Research & Period Analyzer (MDRPA) project must progress through controlled, reviewable, traceable, and scientifically responsible development.