# Backend Integration Specification

**Project:** MEDA Research Workbench  
**Document:** Backend Integration Specification  
**Version:** 1.1 — Revised Draft  
**Target Branch:** `main`

---

## 1. Purpose

This document defines the proposed integration architecture between the existing MEDA scientific analyzers and the MEDA Research Workbench desktop application.

The integration must preserve existing scientific calculations, data interpretation, and analyzer behavior.

The GUI must remain independent of the scientific backend.

This document distinguishes between:

- **Current Source Interface:** Functions and behavior confirmed in the reviewed source code.
- **Proposed Integration Contract:** Future interfaces and responsibilities required to integrate the analyzers into the application.

A proposed contract must not be treated as an already implemented feature.

## 2. Integration Principles

1. Preserve existing scientific logic.
2. Do not modify scientific calculations merely to support GUI integration.
3. Keep every analysis run isolated.
4. Pass explicit input and output paths to analyzers.
5. Keep GUI execution separate from backend execution.
6. Do not treat missing information as zero or as a successful measurement.
7. Preserve analyzer reports and their original meaning.
8. Record configuration and execution metadata for reproducibility.
9. Keep integration adapters separate from scientific analysis logic where practical.
10. Preserve existing standalone CLI behavior where possible.

## 3. Backend Components

| Component | Responsibility |
|---|---|
| `meda_common.py` | Shared time parsing and metadata helpers |
| `file_discovery.py` | Discover and inventory CSV/XML files |
| `xml_parser.py` | Extract XML metadata |
| `coverage_analyzer.py` | Analyze product and Sol coverage |
| `quality_analyzer.py` | Analyze quality candidates, operational fields, uncertainty and documented ranges |
| `synchronization_analyzer.py` | Compare timestamp series between products |
| `period_ranker.py` | Compare and rank candidate periods |

`meda_common.py` is a shared utility module, not an independent pipeline stage.

## 4. Pipeline Execution Order

The intended execution order is:

1. File Discovery
2. XML Parsing
3. Coverage Analysis
4. Quality Analysis
5. Synchronization Analysis
6. Period Ranking

Quality Analysis and Synchronization Analysis may execute independently after the shared inventory and metadata have been generated.

Period Ranking must execute only after all required reports have been generated and validated.

The pipeline coordinator will manage dependencies and execution order. It must not duplicate scientific calculations already implemented in the analyzers.

## 5. Analyzer Interface Contracts

### 5.1 File Discovery

**Module:** `backend/analyzers/file_discovery.py`

**Current Source Interface:**

- `discover_files(input_dir: Path) -> list[dict]`
- `write_inventory(records, output_file)`

Current responsibilities:

- Discover supported CSV and XML files.
- Identify Sol folders and product codes.
- Record file information and CSV/XML relationships.
- Write the inventory CSV through the existing writer function.

**Proposed Integration Contract:**

- Receive an explicit input directory.
- Receive an explicit inventory output path.
- Preserve the existing discovery records.
- Allow the pipeline adapter to produce a structured stage result.

The structured stage result is a proposed adapter responsibility. It must not be assumed to be the current return value of `discover_files`.

Expected artifact:

- `file_inventory.csv`

### 5.2 XML Parser

**Module:** `backend/analyzers/xml_parser.py`

**Current Source Interface:**

- `parse_xml_file(xml_path, input_root=None, include_full_xml=False) -> dict`
- `build_metadata_inventory(input_dir, include_full_xml=False) -> dict`
- `save_json(data, output_file)`

Current responsibilities:

- Parse XML metadata.
- Extract product, table and field metadata.
- Record parsing errors and metadata warnings.
- Preserve positional field information where required.

**Proposed Integration Contract:**

- Receive an explicit input directory.
- Receive an explicit metadata output path.
- Preserve the existing `include_full_xml` option.
- Preserve the existing metadata structure.
- Allow the pipeline adapter to expose parsing results and summaries.

Expected artifact:

- `metadata_inventory.json`

### 5.3 Coverage Analyzer

**Module:** `backend/analyzers/coverage_analyzer.py`

**Current Source Interface:**

- `analyze_coverage(input_dir, inventory_records, metadata, gap_factor=2.5) -> list[dict]`

Current responsibilities:

- Analyze product and Sol coverage.
- Evaluate coverage gaps using the configured gap factor.
- Use inventory records and XML metadata.

**Proposed Integration Contract:**

- Pass explicit input paths and output paths through the integration layer.
- Support configurable Sol range.
- Support configurable gap factor.
- Preserve the current analysis function and its scientific behavior.
- Allow the adapter to write the report and prepare a stage result.

Expected artifacts:

- `coverage_report.csv`
- `coverage_summary.json`

The summary file and structured stage result are integration outputs to be implemented or verified. They must not be assumed to be returned directly by `analyze_coverage`.

### 5.4 Quality Analyzer

**Module:** `backend/analyzers/quality_analyzer.py`

**Current Source Interface:**

- `run_analysis(input_root, inventory, metadata) -> list[dict]`

Current responsibilities:

- Analyze quality-related metadata candidates.
- Keep operational/context fields distinct.
- Identify uncertainty-related fields.
- Apply documented numeric range checks where applicable.

**Proposed Integration Contract:**

- Pass explicit input and output paths through the integration layer.
- Preserve current field classification.
- Preserve documented range-checking behavior.
- Allow the adapter to write the report and prepare a structured stage result.

Expected artifacts:

- `quality_field_report.csv`
- `quality_summary.json`

The summary output and structured stage result are proposed integration responsibilities unless confirmed in the current implementation.

Important:

- Quality candidates, operational/context candidates and uncertainty fields must remain separate categories.
- Do not create an undocumented universal Quality Score.
- Do not interpret Quality Flags without authoritative definitions.

### 5.5 Synchronization Analyzer

**Module:** `backend/analyzers/synchronization_analyzer.py`

**Current Source Interface:**

- `run_analysis(input_root, inventory, metadata_records, tolerance, axis_preference=DEFAULT_AXIS_PREFERENCE) -> tuple[list[dict], list[dict]]`

Current responsibilities:

- Compare timestamp series between products.
- Produce file-level and pair-level synchronization reports.
- Apply the configured tolerance and time-axis preference.
- Preserve duplicate timestamp occurrence behavior.

**Proposed Integration Contract:**

- Pass explicit input and output paths through the integration layer.
- Configure tolerance.
- Configure time-axis preference.
- Preserve both returned report collections.
- Allow the adapter to prepare a structured stage result and summary.

Expected artifacts:

- `synchronization_file_report.csv`
- `synchronization_pair_report.csv`
- `synchronization_summary.json`

The summary output and structured stage result are proposed integration responsibilities unless confirmed in the current implementation.

Important:

- Matching must preserve one-to-one occurrence behavior.
- Duplicate timestamps must not be silently discarded.
- Tolerance must be interpreted in the selected coordinate, not automatically as SI seconds.
- Different products may have different sampling schedules.
- Synchronization match rates are diagnostics, not quality scores.

### 5.6 Period Ranker

**Module:** `backend/analyzers/period_ranker.py`

**Current Source Interface:**

- `run(args) -> dict`

The current ranker is report-file-oriented. It reads report files and writes ranking outputs using paths and options supplied through its arguments.

Current inputs:

- File inventory report.
- Coverage report.
- Quality report.
- Synchronization file report.
- Synchronization pair report.

Current outputs:

- Ranking CSV.
- Ranking summary JSON.

Configuration includes:

- Start Sol.
- End Sol.
- Window size.
- Minimum Sol fraction.
- Minimum metrics.
- Required products.
- Metric weights.
- Integrity weights.

**Proposed Integration Contract:**

- Supply explicit paths for every input report.
- Supply explicit ranking and summary output paths.
- Preserve the current argument-based execution model where practical.
- Allow the pipeline adapter to expose ranking rows and summary information.
- Preserve existing ranking rules and unavailable-metric handling.

Default metric weights:

| Metric | Default Weight |
|---|---:|
| File Availability | 0.20 |
| Data Integrity | 0.45 |
| Quality Indicators | 0.15 |
| Synchronization | 0.20 |

Unavailable metrics must not be fabricated or silently treated as zero.

Existing weight normalization behavior must be preserved.

The ranker must not lower `min_metrics` merely to force a ranking result.

## 6. Metadata Representation at the Pipeline Boundary

The reviewed analyzers do not all consume metadata in the same representation.

Current expectations:

- Coverage Analyzer consumes a metadata dictionary.
- Quality Analyzer consumes a metadata dictionary.
- Synchronization Analyzer consumes a list of metadata records.

The pipeline must handle this difference explicitly.

**Proposed integration approach:**

1. XML Parser generates the existing metadata inventory.
2. The pipeline retains the original metadata structure.
3. An integration adapter extracts the required records for Synchronization Analyzer.
4. Coverage and Quality receive the dictionary representation they currently expect.
5. No scientific information is discarded or reinterpreted during conversion.

This normalization belongs at the pipeline boundary, not inside scientific calculations.

## 7. Run Directory Contract

Every analysis execution must receive a unique Run ID.

Recommended structure:

    user_data/
        runs/
            range_100_150_run_001/
                input/
                output/
                    file_inventory.csv
                    metadata_inventory.json
                    coverage_report.csv
                    coverage_summary.json
                    quality_field_report.csv
                    quality_summary.json
                    synchronization_file_report.csv
                    synchronization_pair_report.csv
                    synchronization_summary.json
                    period_ranking.csv
                    period_ranking_summary.json
                config.json
                run_metadata.json

A second execution of the same Sol range must receive a different Run ID.

Rules:

- Never overwrite another run's output.
- Never use a shared output directory for different runs.
- Store the run configuration.
- Record timestamps, status and application version.
- Keep user data outside the application installation directory.
- Keep run-specific inputs and outputs isolated.

The exact input storage strategy will be finalized during Run Manager design.

## 8. Pipeline Responsibilities

The future pipeline coordinator will:

1. Validate the run configuration.
2. Create and register a unique Run ID.
3. Prepare isolated input and output directories.
4. Execute analyzers in dependency order.
5. Adapt inputs to the existing analyzer interfaces.
6. Validate required intermediate outputs.
7. Record stage status and errors.
8. Stop dependent stages when required inputs are unavailable.
9. Preserve completed stage outputs when a later stage fails.
10. Generate final run metadata.
11. Return a structured execution result to the application.

The pipeline must not contain GUI rendering logic.

Structured stage results are a proposed integration interface. They must not require changes to scientific algorithms.

## 9. Error Handling

Each integration stage should expose:

- Stage name.
- Execution status.
- Start and finish timestamps.
- Input references.
- Output references.
- Warning information.
- Error information.

Suggested statuses:

- `pending`
- `running`
- `completed`
- `completed_with_warnings`
- `failed`
- `cancelled`
- `skipped`

A failed stage must not be reported as successful.

A later stage must not run when its required input is missing or invalid.

Errors must be recorded in run metadata and made available to the GUI.

Warnings must remain distinguishable from errors.

## 10. Background Execution

The GUI must not execute long-running analysis directly on its main thread.

Planned architecture:

- PySide6 worker object.
- QThread-based execution.
- Progress signals.
- Stage completion signals.
- Error signals.
- Cancellation support.
- Safe worker cleanup.

The pipeline should report progress without depending on GUI widgets.

Cancellation must not leave a run incorrectly marked as completed.

## 11. Scientific Integrity Requirements

The integration must preserve these constraints:

1. File availability is not equivalent to data completeness.
2. Data completeness is not equivalent to data quality.
3. Numeric completeness is not scientific validity.
4. XML `valid_minimum` and `valid_maximum` are documented numeric range checks, not universal scientific validity tests.
5. Quality Flags must not be interpreted without authoritative definitions.
6. Operational/context flags and measurement uncertainty must remain distinct.
7. Metadata warnings must not be classified as measurement-quality failures.
8. Mission-specific timestamps must not be converted to UTC without documented authority.
9. LMST and LTST must not be treated as interchangeable time coordinates.
10. Synchronization match rates are diagnostics, not quality scores.
11. Duplicate timestamp occurrences must be preserved according to current analyzer behavior.
12. Partial windows must remain excluded from ranking where current ranking rules require exclusion.
13. The ranking remains exploratory comparative evidence, not scientific certification.

## 12. Required Integration Changes

The following changes are planned, but are not yet authorized for implementation:

- Add explicit path handling to integration interfaces where needed.
- Separate reusable analysis functions from command-line entry points where necessary.
- Introduce integration adapters for standardized stage results.
- Normalize metadata representation at the pipeline boundary.
- Add output validation.
- Add run-specific configuration and metadata handling.
- Add structured progress and error reporting.
- Preserve existing CLI behavior where practical.
- Add integration tests comparing pipeline results with trusted standalone analyzer outputs.

No scientific algorithm should be changed as part of these interface adaptations.

Before changing any analyzer, its current interface and behavior must be documented and tested.

## 13. Testing Requirements

Before accepting backend integration:

- Test each analyzer independently.
- Test missing input files.
- Test invalid input directories.
- Test malformed XML.
- Test missing metadata records.
- Test unresolved CSV paths.
- Test duplicate timestamp occurrences.
- Test different product sampling schedules.
- Test partial Sol windows.
- Test unavailable ranking metrics.
- Test two runs using the same Sol range.
- Verify that run outputs never mix.
- Compare integrated results against trusted standalone analyzer results.
- Verify that adapters do not change scientific report contents.
- Verify that failed stages do not trigger dependent stages.

Tests must distinguish between expected warnings and actual failures.

## 14. Acceptance Criteria

Backend integration will be considered accepted only when:

- All analyzers execute through the pipeline.
- Each run uses isolated paths.
- Existing analyzer interfaces are preserved or changed through explicitly reviewed adapters.
- All required outputs are validated.
- Errors and warnings are recorded accurately.
- Background execution does not freeze the GUI.
- Existing scientific behavior is preserved.
- Integrated results match trusted standalone results within the expected behavior of each analyzer.
- Run isolation tests pass.
- All required integration tests pass.

## 15. Current Status

**Document status:** Revised Draft — awaiting approval.

**Source review status:** Completed for the reviewed analyzer files.

**Test execution status:** Pending.

**Implementation status:** Not started.

The next development task after approval is to create the Backend Interface Audit, documenting the exact current callable signatures, input representations, output behavior, and required adapters for every analyzer.

No analyzer implementation should begin until this audit is reviewed and approved.

---

**End of Document**