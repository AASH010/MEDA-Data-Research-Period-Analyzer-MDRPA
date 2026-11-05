# User Guide

**Project:** MEDA Data Research & Period Analyzer (MDRPA)  
**Document:** User Guide  
**Version:** 2.0 — Proposed  
**Target Branch:** `main`

---

# Part I — Project Overview and Current Backend Usage

## 1. Introduction

MEDA Data Research & Period Analyzer (MDRPA) is a scientific data exploration application designed to help users inspect, analyze, and compare candidate observation periods using calibrated MEDA data collected by the Mars 2020 Perseverance rover.

The project provides analytical tools for examining:

- MEDA data availability.
- Measurement and timestamp completeness.
- XML metadata.
- Quality-related metadata candidates.
- Measurement uncertainty information.
- Temporal synchronization between products.
- Exploratory candidate-period ranking.

MDRPA is designed to support scientific investigation and research planning.

It does not certify scientific validity or replace official NASA/PDS documentation and scientific interpretation.

## 2. Application Versions and Feature Status

This guide covers two complementary parts of the project.

### 2.1 Current Backend Version

The current backend consists of independent Python command-line analyzers.

Users can execute the available analyzers individually to generate scientific and technical reports.

<badge color="success">Available in source</badge>

- File Discovery.
- XML Metadata Parsing.
- Coverage Analysis.
- Quality Analysis.
- Synchronization Analysis.
- Period Ranking.

Availability in source does not automatically mean every execution path has passed acceptance testing.

### 2.2 Planned Desktop Application

The target product is a Windows desktop application with a graphical interface.

Its planned capabilities include:

- First-launch tutorial.
- Main Window and Navigation.
- Input Manager.
- Analysis Configuration.
- Analysis Center.
- Run Manager.
- Results Dashboard.
- Reports and Export.
- Help, About, and Credits.

<badge color="warning">Planned</badge>

These capabilities must not be considered available until implemented and tested.

## 3. Feature Status Labels

This guide uses the following terminology:

| Status | Meaning |
|---|---|
| Available | Implemented and verified for the stated functionality |
| Under Development | Implementation has started but is not yet accepted |
| Planned | Approved design or future functionality not yet implemented |

A feature must not be marked Available merely because its directory, Python file, or interface placeholder exists.

## 4. Project Requirements

### 4.1 Current Backend Requirements

- Python 3.10 or newer.
- Git.
- Terminal or command-line interface.
- Required Python packages.
- Sufficient disk space for input datasets and generated reports.

### 4.2 Planned Desktop Requirements

The target desktop application is designed for Windows.

The planned technology stack includes:

- Python.
- PySide6.
- PyQtGraph.
- NumPy.
- Pandas.
- Matplotlib where appropriate.
- PyInstaller for Windows packaging.

The final supported Windows versions and minimum hardware requirements will be documented after packaging and compatibility testing.

## 5. Obtain the Project

Official repository:

https://github.com/AASH010/MEDA-Data-Research-Period-Analyzer-MDRPA

Clone the repository:

```bash
git clone https://github.com/AASH010/MEDA-Data-Research-Period-Analyzer-MDRPA.git
```

Enter the project directory:

```bash
cd MEDA-Data-Research-Period-Analyzer-MDRPA
```

The official development branch is `main`.

---

# Part II — Current Backend User Guide

## 6. Prepare the Python Environment

### 6.1 Create a Virtual Environment

```bash
python -m venv .venv
```

### 6.2 Activate the Environment

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Windows Command Prompt:

```cmd
.venv\Scripts\activate.bat
```

Linux/macOS:

```bash
source .venv/bin/activate
```

### 6.3 Install Dependencies

Upgrade pip:

```bash
python -m pip install --upgrade pip
```

Install project dependencies:

```bash
python -m pip install -r requirements.txt
```

The current requirements file includes:

- PySide6.
- PyQtGraph.
- NumPy.
- Pandas.
- PyYAML.
- Python-dateutil.
- lxml.

Installing GUI dependencies does not mean the desktop application is already implemented.

## 7. Obtain MEDA Data

The primary source for the project dataset is NASA's Planetary Data System (PDS), specifically the PDS Atmospheres Node.

Official resources:

- MEDA documentation:  
  https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/PERSEVERANCE/meda.html

- Calibrated MEDA data:  
  https://atmos.nmsu.edu/PDS/data/PDS4/Mars2020/mars2020_meda/data_calibrated_env/

Use the appropriate calibrated MEDA products.

Preserve original filenames and source file contents.

Do not manually modify original scientific data files to force compatibility with the application.

## 8. Organize the Input Dataset

The current analyzers expect a root directory containing Sol folders.

Example:

```text
input/
├── SOL_0100/
│   ├── original_product_file_1.CSV
│   ├── original_product_file_1.XML
│   └── ...
├── SOL_0101/
│   ├── original_product_file_2.CSV
│   ├── original_product_file_2.XML
│   └── ...
└── SOL_0102/
    └── ...
```

Supported Sol folder naming patterns include:

- `SOL100`
- `SOL_0100`
- `SOL-100`

CSV and XML files should retain their original official filenames.

Whenever available, provide the corresponding XML metadata for each CSV measurement file.

The discovery analyzer records missing or unresolved file relationships.

## 9. Current Backend Analysis Workflow

The current standalone workflow follows this order:

1. File Discovery.
2. XML Metadata Parsing.
3. Coverage Analysis.
4. Quality Analysis.
5. Synchronization Analysis.
6. Period Ranking.

The current repository does not yet provide a unified command that executes the entire workflow.

Each analyzer must be executed separately.

All commands below assume execution from the project root.

## 10. Execute the Current Analyzers

### 10.1 File Discovery

**Module:**

`backend/analyzers/file_discovery.py`

Execute:

```bash
python -m backend.analyzers.file_discovery
```

With explicit paths:

```bash
python -m backend.analyzers.file_discovery --input input --output output/file_inventory.csv
```

The analyzer discovers supported CSV and XML files and records information such as:

- Sol number.
- Product code.
- Filename.
- File extension.
- File size.
- CSV/XML relationships.
- Discovery issues.

Default output:

```text
output/file_inventory.csv
```

Review the inventory before proceeding.

### 10.2 XML Metadata Parsing

**Module:**

`backend/analyzers/xml_parser.py`

Execute:

```bash
python -m backend.analyzers.xml_parser
```

With explicit paths:

```bash
python -m backend.analyzers.xml_parser --input input --output output/metadata_inventory.json
```

To include the complete parsed XML structure:

```bash
python -m backend.analyzers.xml_parser --include-full-xml
```

The full XML option may substantially increase output file size.

Default output:

```text
output/metadata_inventory.json
```

The metadata inventory contains extracted product, table, and field information.

A successful XML parse does not establish scientific validity.

### 10.3 Coverage Analysis

**Module:**

`backend/analyzers/coverage_analyzer.py`

Execute:

```bash
python -m backend.analyzers.coverage_analyzer
```

Example Sol range:

```bash
python -m backend.analyzers.coverage_analyzer --start-sol 100 --end-sol 150
```

Example with explicit paths and gap factor:

```bash
python -m backend.analyzers.coverage_analyzer --input input --inventory output/file_inventory.csv --metadata output/metadata_inventory.json --output output/coverage_report.csv --summary output/coverage_summary.json --start-sol 100 --end-sol 150 --gap-factor 2.5
```

The analyzer examines:

- CSV row counts.
- Time fields and time-axis kinds.
- Parsed, missing, and invalid timestamps.
- Duplicate and out-of-order timestamps.
- Temporal coverage.
- Detected timestamp gaps.
- Numeric value completeness.
- CSV/XML column mapping.

Default outputs:

```text
output/coverage_report.csv
output/coverage_summary.json
```

Detected gaps are diagnostics. They do not establish why observations are missing or provide a scientifically validated estimate of missing measurement duration.

### 10.4 Quality Analysis

**Module:**

`backend/analyzers/quality_analyzer.py`

Execute:

```bash
python -m backend.analyzers.quality_analyzer
```

Example with explicit paths:

```bash
python -m backend.analyzers.quality_analyzer --input input --inventory output/file_inventory.csv --metadata output/metadata_inventory.json --output output/quality_field_report.csv --summary output/quality_summary.json
```

The analyzer examines:

- Quality-related field candidates.
- Operational/context field candidates.
- Measurement uncertainty candidates.
- Documented XML numerical bounds.

Default outputs:

```text
output/quality_field_report.csv
output/quality_summary.json
```

Do not infer the meaning of Quality Flags from their names alone.

Values outside documented XML bounds require review and are not automatically scientifically invalid.

### 10.5 Synchronization Analysis

**Module:**

`backend/analyzers/synchronization_analyzer.py`

Execute:

```bash
python -m backend.analyzers.synchronization_analyzer
```

Example:

```bash
python -m backend.analyzers.synchronization_analyzer --input input --inventory output/file_inventory.csv --metadata output/metadata_inventory.json --tolerance 1.0
```

Example time-axis preference:

```bash
python -m backend.analyzers.synchronization_analyzer --time-axis SCLK UTC LMST LTST ISO_NAIVE
```

Default outputs:

```text
output/synchronization_file_report.csv
output/synchronization_pair_report.csv
output/synchronization_summary.json
```

Synchronization reports describe temporal matching between product records.

Tolerance applies to the selected coordinate and is not guaranteed to represent SI seconds for every time axis.

A timestamp match does not establish scientific equivalence.

### 10.6 Period Ranking

**Module:**

`backend/analyzers/period_ranker.py`

Execute:

```bash
python -m backend.analyzers.period_ranker
```

Example:

```bash
python -m backend.analyzers.period_ranker --start-sol 100 --end-sol 150 --window-size 10
```

Example required products:

```bash
python -m backend.analyzers.period_ranker --required-products ATS PS RDS RHS TIRS WS
```

Example ranking weights:

```bash
python -m backend.analyzers.period_ranker --weight-files 0.20 --weight-integrity 0.45 --weight-quality 0.15 --weight-sync 0.20
```

The ranker consumes the reports generated by the previous stages.

Default output:

```text
output/period_ranking.csv
output/period_ranking_summary.json
```

Default ranking settings:

| Setting | Default |
|---|---:|
| Window size | 10 Sols |
| Minimum Sol fraction | 0.5 |
| Minimum metrics | 3 |
| File availability weight | 0.20 |
| Data integrity weight | 0.45 |
| Quality indicator weight | 0.15 |
| Synchronization weight | 0.20 |

Default required products:

- ATS
- PS
- RDS
- RHS
- TIRS
- WS

ENG is optional by default.

Unavailable metrics are not fabricated as zero. Available positive weights are renormalized.

Partial windows are reported separately and are not ranked against full windows.

Candidate rankings are exploratory comparisons, not scientific certification.

## 11. Current Backend Output Management

The standalone analyzers use shared default paths under:

```text
input/
output/
```

Repeated executions using the same output paths may overwrite previous results.

Until the Run Manager is implemented, users should maintain separate output locations or working copies for separate analysis executions.

Preserve:

- Original input files.
- Inventory reports.
- Metadata inventory.
- Analyzer reports.
- Ranking outputs.
- Exact command-line arguments.
- Project version or commit identifier.

Do not combine reports from different datasets or configurations.

---

# Part III — Target Windows Desktop Application User Guide

## 12. Desktop Application Overview

The target MDRPA product is a Windows desktop application designed to provide a unified graphical workflow.

Instead of requiring users to execute separate Python commands, the desktop application will coordinate input preparation, analysis configuration, execution, result inspection, and reporting through a graphical interface.

<badge color="warning">Planned product functionality</badge>

The following sections describe the approved target application design.

They are not claims that these screens or features have already been implemented.

## 13. First Launch and Tutorial

### 13.1 First Launch

On the first successful application launch, the user will be presented with an introductory tutorial.

The tutorial is designed to explain the application's purpose, structure, and basic workflow.

### 13.2 Tutorial Behavior

The approved tutorial behavior is:

- Display automatically on first launch.
- Use a sequence of informational pages.
- Do not require interaction with example data.
- Provide a `Next` button to move forward.
- Provide a `Finish` button on the final page.
- Do not include Back or Skip buttons.
- Allow the tutorial to be reopened from Help.

The tutorial is informational and must not execute analysis operations.

### 13.3 Tutorial Completion

After the user finishes the tutorial, the application will open its main window.

The completion state should be retained so the tutorial does not automatically reappear on every launch.

## 14. Main Window and Navigation

The Main Window will provide the primary application workspace.

The approved visual direction is a formal Classic Windows design.

### 14.1 Visual Style

The target interface uses:

- Grey and white surfaces.
- Soft blue accents.
- Clear section separation.
- Restrained visual effects.
- Consistent typography.
- Standard desktop interaction patterns.

The interface should prioritize readability and functional clarity over decorative design.

### 14.2 Navigation Structure

The planned main navigation contains:

1. Input Manager.
2. Analysis Configuration.
3. Analysis Center.
4. Results Dashboard.
5. Reports & Export.
6. Help / About / Credits.

The navigation should make the current workspace clear and provide predictable movement between application sections.

## 15. Input Manager

**Status:** Planned.

The Input Manager will allow users to prepare and manage MEDA datasets before analysis.

### 15.1 Main Responsibilities

- Select an input dataset directory.
- Inspect available Sol folders.
- Discover supported CSV and XML files.
- Display discovered products.
- Identify missing or unmatched file counterparts.
- Review input structure.
- Check whether required input files are available.

### 15.2 Dataset Inspection

The user should be able to review:

- Dataset root directory.
- Available Sol range.
- Available products.
- CSV/XML file counts.
- Missing counterparts.
- Discovery warnings.
- Input preparation status.

### 15.3 Input Integrity

The application must preserve original scientific files.

It must not silently rename, rewrite, or modify original MEDA data to force compatibility.

Any future data-preparation operation must be clearly documented and traceable.

## 16. Analysis Configuration

**Status:** Planned.

Analysis Configuration will allow users to define the parameters of an analysis run before execution.

### 16.1 Sol Range

The user will specify:

- Starting Sol.
- Ending Sol.
- Candidate window size.

The application should validate the selected range and provide clear feedback for invalid configurations.

### 16.2 Analysis Parameters

Depending on the implemented backend configuration interface, the user may configure:

- Required products.
- Minimum Sol fraction.
- Minimum available metrics.
- Timestamp gap factor.
- Synchronization tolerance.
- Time-axis preference.
- Ranking metric weights.

### 16.3 Ranking Weights

The default ranking weights are:

| Metric | Default |
|---|---:|
| File Availability | 0.20 |
| Data Integrity | 0.45 |
| Quality Indicators | 0.15 |
| Synchronization | 0.20 |

These weights are exploratory software parameters.

The application must explain that changing them changes the comparison methodology.

### 16.4 Configuration Validation

Before a run starts, the application should verify:

- Valid Sol range.
- Valid numerical parameters.
- Valid weight configuration.
- Required input availability.
- Compatible execution settings.

Invalid configurations must be reported clearly.

## 17. Analysis Center

**Status:** Planned.

The Analysis Center will provide the main interface for starting and monitoring analysis operations.

### 17.1 Starting an Analysis

The intended workflow is:

1. Select the prepared dataset.
2. Open Analysis Configuration.
3. Review the analysis parameters.
4. Validate the configuration.
5. Start a new analysis run.
6. Monitor execution progress.
7. Inspect the final execution status.

The application must not report successful completion before the backend confirms it.

### 17.2 Execution Progress

The Analysis Center is expected to display:

- Current execution stage.
- Completed stages.
- Pending stages.
- Progress information where available.
- Warnings.
- Errors.
- Final run status.

Progress information must represent actual backend execution.

### 17.3 Cancellation

If cancellation is supported by the final execution engine, the user will be able to request cancellation of an active run.

The application must record cancellation accurately and must not mark a cancelled run as completed.

### 17.4 Error Reporting

When a stage fails, the application should display:

- Failed stage.
- Error description.
- Relevant diagnostic information.
- Available completed outputs.
- Whether dependent stages were skipped.

A failure in one run must not corrupt another run.

## 18. Run Management

**Status:** Planned.

Run Management will organize each analysis execution independently.

### 18.1 Unique Run IDs

Every analysis execution must receive a unique Run ID.

Example:

```text
range_100_150_run_001
range_100_150_run_002
```

Two runs using the same Sol range must still receive different IDs.

### 18.2 Run Isolation

Each run must have its own input references, configuration, metadata, and output directory.

Recommended structure:

```text
user_data/
└── runs/
    ├── range_100_150_run_001/
    │   ├── input/
    │   ├── output/
    │   ├── config.json
    │   ├── run_metadata.json
    │   └── logs/
    │
    └── range_100_150_run_002/
        ├── input/
        ├── output/
        ├── config.json
        ├── run_metadata.json
        └── logs/
```

### 18.3 Run History

The planned Run Manager will maintain information such as:

- Run ID.
- Selected Sol range.
- Start time.
- Completion time.
- Execution status.
- Configuration.
- Output location.
- Error information, where applicable.

### 18.4 Run Status

The intended run statuses are:

| Status | Meaning |
|---|---|
| Pending | Created but not started |
| Running | Currently executing |
| Completed | Finished successfully |
| Failed | Execution failed |
| Cancelled | Execution was cancelled |

### 18.5 Run Protection

The Run Manager must:

- Prevent Run ID collisions.
- Prevent accidental overwriting.
- Keep different run outputs isolated.
- Preserve completed reports after later-stage failures.
- Keep user data outside the application installation directory.

## 19. Results Dashboard

**Status:** Planned.

The Results Dashboard will provide a visual overview of completed analysis results.

### 19.1 Summary Information

The planned dashboard may present:

- Selected Sol range.
- Number of discovered files.
- Product availability.
- Coverage summary.
- Quality-related report counts.
- Synchronization summary.
- Number of candidate windows.
- Number of rankable windows.
- Number of partial windows.
- Ranking summary.

### 19.2 Candidate Period Comparison

The dashboard should allow users to compare candidate windows using:

- Exploratory score.
- Available metrics.
- Individual metric scores.
- Comparison group.
- Ranking status.
- Explanatory information.

### 19.3 Charts and Visualization

Depending on the final implementation, the dashboard may include:

- Product availability charts.
- Temporal coverage plots.
- Data completeness charts.
- Synchronization comparison charts.
- Candidate period score charts.

Charts must identify the displayed metric and its interpretation.

Unavailable values must not be displayed as measured zeros.

### 19.4 Ranking Interpretation

The dashboard must clearly distinguish between:

- Rankable windows.
- Partial windows.
- Insufficient-data windows.
- Different metric comparison groups.

Scores from different comparison groups must not be presented as directly equivalent.

A high exploratory score does not establish scientific superiority for every research objective.

## 20. Reports and Export

**Status:** Planned.

The Reports & Export workspace will provide access to generated analytical reports.

### 20.1 Available Report Categories

The intended report categories include:

- File Inventory.
- XML Metadata Inventory.
- Coverage Report.
- Quality Field Report.
- Synchronization File Report.
- Synchronization Pair Report.
- Period Ranking Report.
- Run Summary.

### 20.2 Report Inspection

Users should be able to:

- Open reports.
- Inspect tables.
- Review warnings.
- Examine summary information.
- Identify the source Run ID.
- Navigate between related reports.

### 20.3 Export

The final application may provide export options for supported formats.

Each export must preserve:

- Run ID.
- Relevant configuration.
- Report identity.
- Data provenance.
- Scientific interpretation limitations.

The exact supported export formats will be confirmed after implementation and testing.

## 21. Help, About, and Credits

**Status:** Planned.

The Help section will provide access to:

- User documentation.
- First-launch tutorial.
- Application workflow explanation.
- Scientific methodology guidance.
- Troubleshooting information.

### 21.1 About

The About section will display:

- Full application name.
- Project version.
- Application description.
- Development information.

### 21.2 Credits

The Credits section will acknowledge the project author and relevant contributions.

Personal contact details and external profile links will only be displayed after they have been explicitly supplied and approved.

## 22. Application Settings

**Status:** Planned.

The application may provide settings for:

- Theme-related preferences, where supported.
- Default input location.
- User data location.
- Tutorial reopening.
- Application preferences.

Settings must not silently change scientific analysis parameters.

Scientific configuration must remain traceable to its associated run.

## 23. Windows Packaging and Installation

**Status:** Planned.

The target release is a Windows executable application.

The packaging process is expected to include:

- Application executable.
- Application icon.
- Required dependencies.
- Appropriate resource files.
- User data directory handling.
- Installer or distribution package.

The application must not store user-generated results inside protected installation directories.

Installation and upgrade instructions will be finalized after packaging tests.

---

# Part IV — Common Troubleshooting

## 24. Backend Troubleshooting

### 24.1 Input Directory Not Found

Check the current working directory and supplied input path.

### 24.2 No Files Discovered

Check Sol folder naming, file extensions, and dataset organization.

### 24.3 Missing XML Counterparts

Inspect the inventory and verify the original dataset.

### 24.4 XML Parsing Failure

Inspect the parsing status and error information in the metadata inventory.

### 24.5 Ambiguous CSV/XML Mapping

Inspect the mapping diagnostics.

Do not manually reorder scientific measurements without an authoritative basis.

### 24.6 No Rankable Candidate Windows

Review:

- Available metric counts.
- Selected Sol range.
- Required products.
- Minimum Sol fraction.
- Minimum metric requirement.
- Upstream reports.

Do not lower the minimum metric requirement simply to force ranking output.

### 24.7 Unavailable Quality Indicator

An unavailable metric may indicate that suitable documented numerical bounds are absent.

It does not prove that all measurements are valid or invalid.

### 24.8 Low Synchronization Match Rate

Review:

- Selected time axis.
- Tolerance.
- Common temporal overlap.
- Product sampling schedules.
- Missing and invalid timestamps.

A low match rate does not independently establish instrument malfunction.

## 25. Desktop Application Troubleshooting

The following are planned support scenarios for the target application.

### 25.1 Application Does Not Start

The final application should provide clear startup diagnostics.

Users should verify that the installed application version is supported and that required files are available.

### 25.2 Dataset Cannot Be Selected

Check directory permissions and confirm that the selected directory contains the expected MEDA Sol folder structure.

### 25.3 Analysis Cannot Start

Review configuration validation messages and confirm that required input files are available.

### 25.4 Analysis Stops Unexpectedly

Inspect the run status and execution log.

A failed run must retain its correct status and available diagnostic information.

### 25.5 Results Are Missing

Verify the Run ID and inspect the corresponding output directory.

The application must not mix results from different runs.

### 25.6 Dashboard and Report Values Differ

The dashboard and reports must reference the same completed run and underlying artifacts.

Any discrepancy should be reported with the Run ID and affected report names.

---

# Part V — Scientific Interpretation and Reproducibility

## 26. Scientific Use and Limitations

Users must preserve the following distinctions:

1. File availability is not data completeness.
2. Data completeness is not scientific validity.
3. Numeric parsing success is not measurement correctness.
4. XML numerical bounds are not universal scientific validity criteria.
5. Quality Flags must not be interpreted without authoritative definitions.
6. Operational/context fields are distinct from measurement-quality information.
7. Measurement uncertainty must retain its documented meaning.
8. Metadata warnings are not automatically measurement-quality failures.
9. Mission-specific timestamps must not be converted to UTC without documented authority.
10. Synchronization match rates are diagnostics, not quality scores.
11. Duplicate timestamp occurrences must not be silently discarded.
12. Partial candidate windows must not be presented as directly ranked against full windows.
13. MEDA observations represent measurements at the rover location and observation times.
14. Candidate rankings are exploratory comparisons, not scientific certification.

For detailed scientific interpretation, consult:

`docs/scientific_methodology.md`

## 27. Reproducibility

For each analysis, preserve:

- Original dataset.
- Project version or commit identifier.
- Selected Sol range.
- Analysis configuration.
- Exact command-line arguments or GUI configuration.
- Generated reports.
- Run ID, when Run Manager is available.
- Relevant logs and warnings.

The application should make it possible to trace every result back to its source run and configuration.

Do not mix reports from different runs.

## 28. Reporting Issues

When reporting a technical issue, provide:

- Application or analyzer name.
- Project version or commit identifier.
- Run ID, if available.
- Exact command executed or GUI workflow followed.
- Relevant error message.
- Affected input file or report.
- Expected behavior.
- Actual behavior.

Do not share passwords, private credentials, or sensitive personal information.

## 29. Related Documentation

- `README.md` — Project overview and objectives.
- `docs/development_guide.md` — Development workflow and change control.
- `docs/architecture.md` — System architecture.
- `docs/analyzer_documentation.md` — Backend analyzer reference.
- `docs/backend_integration_specification.md` — Backend integration architecture.
- `docs/scientific_methodology.md` — Scientific methodology and limitations.

## 30. Governing Principle

**MDRPA is designed to make MEDA data exploration systematic, traceable, and reproducible. Users must preserve original data, understand the meaning and limitations of analytical indicators, and distinguish the capabilities of the current backend from the planned desktop application. No exploratory score or ranking should be interpreted as scientific certification.**