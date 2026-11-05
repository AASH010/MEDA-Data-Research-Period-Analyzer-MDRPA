# Backend Integration Specification

**Project:** MEDA Research Workbench  
**Document:** Backend Integration Specification  
**Version:** 1.0 — Draft  
**Target Branch:** `main`

---

## 1. Purpose

This document defines how the existing MEDA scientific analyzers will integrate with the MEDA Research Workbench desktop application.

The integration must preserve existing scientific calculations, data interpretation, and analyzer behavior.

The GUI must remain independent of the scientific backend.

## 2. Integration Principles

1. Preserve existing scientific logic.
2. Do not modify scientific calculations merely to support GUI integration.
3. Keep every analysis run isolated.
4. Pass explicit input and output paths to analyzers.
5. Keep GUI execution separate from backend execution.
6. Do not treat missing information as zero or as a successful measurement.
7. Preserve analyzer reports and their original meaning.
8. Record configuration and execution metadata for reproducibility.

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

## 5. Analyzer Interface Contracts

### 5.1 File Discovery

**Module:** `backend/analyzers/file_discovery.py`

Input:
- Input directory containing MEDA Sol folders.

Processing:
- Recursively discover supported CSV and XML files.
- Identify Sol folders and product codes.
- Record file information and CSV/XML relationships.

Output:
- `file_inventory.csv`

Required integration interface:
- Explicit input directory.
- Explicit inventory output path.
- Structured return value containing discovered records and execution summary.

### 5.2 XML Parser

**Module:** `backend/analyzers/xml_parser.py`

Input:
- Input directory containing XML files.

Processing:
- Parse XML metadata.
- Extract product, table and field metadata.
- Record parsing errors and metadata warnings separately.
- Preserve positional field information where required.

Output:
- `metadata_inventory.json`

Required integration interface:
- Explicit input directory.
- Explicit metadata output path.
- Preserve the existing `include_full_xml` option.
- Return metadata records and parsing summary.

### 5.3 Coverage Analyzer

**Module:** `backend/analyzers/coverage_analyzer.py`

Inputs:
- Input directory.
- File inventory records.
- XML metadata.
- Configurable gap factor.

Outputs:
- `coverage_report.csv`
- `coverage_summary.json`

Required integration interface:
- Explicit input and output paths.
- Configurable Sol range.
- Configurable gap factor.
- Return report records and summary.

### 5.4 Quality Analyzer

**Module:** `backend/analyzers/quality_analyzer.py`

Inputs:
- Input directory.
- File inventory records.
- XML metadata.

Outputs:
- `quality_field_report.csv`
- `quality_summary.json`

Required integration interface:
- Explicit input and output paths.
- Return report records and summary.
- Preserve existing field classification and documented range-checking behavior.

Important:
- Quality candidates, operational/context candidates and uncertainty fields must remain separate categories.
- Do not create an undocumented universal Quality Score.

### 5.5 Synchronization Analyzer

**Module:** `backend/analyzers/synchronization_analyzer.py`

Inputs:
- Input directory.
- File inventory records.
- XML metadata records.
- Timestamp tolerance.
- Time-axis preference.

Outputs:
- `synchronization_file_report.csv`
- `synchronization_pair_report.csv`
- `synchronization_summary.json`

Required integration interface:
- Explicit input and output paths.
- Configurable tolerance.
- Configurable time-axis preference.
- Return file reports, pair reports and summary.

Important:
- Matching must preserve one-to-one occurrence behavior.
- Duplicate timestamps must not be silently discarded.
- Tolerance must be interpreted in the selected coordinate, not automatically as SI seconds.

### 5.6 Period Ranker

**Module:** `backend/analyzers/period_ranker.py`

Inputs:
- File inventory report.
- Coverage report.
- Quality report.
- Synchronization file report.
- Synchronization pair report.

Outputs:
- `period_ranking.csv`
- `period_ranking_summary.json`

Configuration:
- Start Sol.
- End Sol.
- Window size.
- Minimum Sol fraction.
- Minimum metrics.
- Required products.
- Metric weights.
- Integrity weights.

Required integration interface:
- Explicit paths for every input report.
- Explicit ranking and summary output paths.
- Return ranking rows and summary.
- Preserve current ranking rules and unavailable-metric handling.

Default metric weights must remain configurable and documented:

| Metric | Default Weight |
|---|---:|
| File Availability | 0.20 |
| Data Integrity | 0.45 |
| Quality Indicators | 0.15 |
| Synchronization | 0.20 |

Unavailable metrics must not be fabricated or silently treated as zero. Existing weight normalization behavior must be preserved.

## 6. Run Directory Contract

Every analysis execution must receive a unique Run ID.

Recommended structure:

    user_data/
        runs/
            range_100_150_run_001/
                input/
                output/
                config.json
                run_metadata.json

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

A second execution of the same Sol range must receive a different Run ID.

Rules:
- Never overwrite another run's output.
- Never use a shared output directory for different runs.
- Store the run configuration.
- Record timestamps, status and application version.
- Keep user data outside the application installation directory.

## 7. Pipeline Responsibilities

The future pipeline coordinator will:

1. Validate the run configuration.
2. Create and register a unique Run ID.
3. Prepare isolated input and output directories.
4. Execute analyzers in dependency order.
5. Validate required intermediate outputs.
6. Record stage status and errors.
7. Stop dependent stages when required inputs are unavailable.
8. Preserve completed stage outputs when a later stage fails.
9. Generate final run metadata.
10. Return a structured execution result to the application.

The pipeline must not contain GUI rendering logic.

## 8. Error Handling

Each stage should expose:

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

Errors must be recorded in the run metadata and made available to the GUI.

## 9. Background Execution

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

## 10. Scientific Integrity Requirements

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
11. Partial windows must remain excluded from ranking where current ranking rules require exclusion.
12. The ranking remains exploratory comparative evidence, not scientific certification.

## 11. Required Integration Changes

The following changes are planned, but not yet authorized for implementation:

- Add explicit path handling to analyzer interfaces where needed.
- Separate reusable analysis functions from command-line entry points.
- Standardize structured stage results.
- Standardize metadata input representation at the pipeline boundary.
- Add output validation.
- Add run-specific configuration and metadata handling.
- Add structured progress and error reporting.
- Preserve existing CLI behavior where practical.
- Add integration tests comparing new pipeline results with trusted analyzer outputs.

No scientific algorithm should be changed as part of these interface adaptations.

## 12. Testing Requirements

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

## 13. Acceptance Criteria

Backend integration will be considered accepted only when:

- All analyzers execute through the pipeline.
- Each run uses isolated paths.
- All required outputs are validated.
- Errors and warnings are recorded accurately.
- Background execution does not freeze the GUI.
- Existing scientific behavior is preserved.
- Integrated results match trusted standalone results within the expected behavior of each analyzer.
- Run isolation tests pass.

## 14. Current Status

**Document status:** Draft — awaiting review.

**Implementation status:** Not started.

The next development task after approval is to create the Backend Interface Audit and define the exact callable contracts and return structures for every analyzer.

---

**End of Document**