# MEDA Data Research & Period Analyzer (MDRPA)

### A Scientific Data Exploration, Analysis, and Candidate Period Ranking Platform for NASA Perseverance MEDA Data

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Application](https://img.shields.io/badge/Application-Desktop%20GUI-purple)
![Status](https://img.shields.io/badge/Development-In%20Progress-orange)

---

## 1. Overview

**MEDA Data Research & Period Analyzer (MDRPA)** is an independent scientific research application designed to explore, inspect, analyze, and compare environmental datasets collected by the Mars Environmental Dynamics Analyzer (MEDA) aboard NASA's Perseverance rover.

The project focuses on organizing and examining calibrated MEDA data, including:

- File availability and organization.
- XML metadata and field definitions.
- Temporal coverage and timestamp characteristics.
- Data completeness and numerical characteristics.
- Quality-related indicators and measurement uncertainty.
- Temporal relationships between different MEDA products.
- Comparative evaluation of candidate observation periods.

MDRPA aims to provide a structured and reproducible workflow that helps researchers investigate MEDA datasets and identify candidate periods for further research.

The project is being developed as a standalone Windows desktop application with a graphical interface for input management, analysis configuration, execution, visualization, and report exploration.

**MDRPA is an analytical research-support tool. It does not replace official instrument documentation, scientific validation, or expert interpretation.**

---

## 2. Research Objectives

The main objectives of MDRPA are:

1. **Dataset Exploration** — Discover and organize MEDA products across selected Sol ranges.
2. **Metadata Inspection** — Extract and inspect XML metadata, field definitions, units, and documented numerical ranges.
3. **Temporal Coverage Assessment** — Examine timestamp availability, missing observations, duplicates, and temporal coverage.
4. **Data Completeness Assessment** — Investigate missing, non-numeric, and other data characteristics.
5. **Quality-Related Analysis** — Preserve and examine documented quality-related fields, operational/context indicators, and measurement uncertainty without assigning undocumented meanings.
6. **Synchronization Analysis** — Investigate temporal relationships and timestamp matching between different MEDA products.
7. **Candidate Period Evaluation** — Compare observation windows using available and documented analytical indicators.
8. **Reproducible Research** — Preserve analysis configurations, metadata, and generated reports for independent review and comparison.

---

## 3. Data Source

The primary data source is NASA's Planetary Data System (PDS), specifically the PDS Atmospheres Node.

| Attribute | Description |
|---|---|
| Mission | Mars 2020 |
| Rover | Perseverance |
| Instrument | Mars Environmental Dynamics Analyzer (MEDA) |
| Dataset | Calibrated environmental data |
| Primary Formats | CSV and XML |
| Data Repository | NASA PDS Atmospheres Node |

### Official Resources

- [NASA PDS MEDA Documentation](https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/PERSEVERANCE/meda.html)
- [MEDA Calibrated Data Directory](https://atmos.nmsu.edu/PDS/data/PDS4/Mars2020/mars2020_meda/data_calibrated_env/)

MDRPA is designed to preserve original NASA filenames and associate measurement files with their corresponding metadata whenever possible.

---

## 4. Core Analysis Modules

The scientific analysis modules are maintained in `backend/analyzers/`.

### 4.1 File Discovery

**Module:** `file_discovery.py`

Responsible for discovering and inventorying MEDA input files.

Main responsibilities:

- Detect Sol directories.
- Extract Sol numbers from supported directory and filename patterns.
- Identify MEDA product codes.
- Discover CSV and XML files.
- Identify corresponding CSV/XML files.
- Record missing counterparts and file-related issues.
- Generate a structured file inventory.

### 4.2 XML Metadata Parser

**Module:** `xml_parser.py`

Responsible for extracting metadata and field definitions from XML products.

Main responsibilities:

- Parse XML metadata structures.
- Extract product and table information.
- Extract field names and data types.
- Extract descriptions and measurement units.
- Preserve documented numerical ranges and special constants.
- Identify potential time-related and quality-related fields.
- Record metadata warnings and parsing issues.

### 4.3 Coverage Analyzer

**Module:** `coverage_analyzer.py`

Responsible for examining file-level and temporal coverage.

Main responsibilities:

- Analyze available CSV products.
- Count data records.
- Identify candidate timestamp fields.
- Parse supported timestamp representations.
- Determine interpretable temporal boundaries.
- Count parsed, missing, invalid, and duplicate timestamps where applicable.
- Examine temporal gaps and sampling characteristics.
- Summarize product availability across selected Sol ranges.

### 4.4 Quality Analyzer

**Module:** `quality_analyzer.py`

Responsible for examining field-level data characteristics and documented numerical boundaries.

Main responsibilities:

- Identify candidate quality-related fields.
- Keep quality-related candidates distinct from operational/context fields.
- Identify uncertainty-related fields.
- Examine missing and non-empty values.
- Examine numeric and non-numeric values.
- Examine distinct values and field characteristics.
- Apply documented numerical range checks where applicable.
- Preserve field values without assigning undocumented meanings.

The analyzer does not assume that every field containing words such as `flag`, `status`, or `quality` has a known scientific interpretation.

### 4.5 Synchronization Analyzer

**Module:** `synchronization_analyzer.py`

Responsible for examining temporal relationships between different MEDA products.

Main responsibilities:

- Identify candidate timestamp fields.
- Parse supported timestamp representations.
- Compare temporal coverage between products.
- Identify matching and unmatched timestamps.
- Examine timestamp differences.
- Apply a configurable matching tolerance.
- Preserve duplicate timestamp occurrences during matching.
- Produce file-level and pair-level synchronization reports.

The selected time coordinate and its interpretation must be considered when evaluating matching tolerance.

### 4.6 Period Ranker

**Module:** `period_ranker.py`

Responsible for comparing and ranking candidate Sol windows using generated analysis reports.

Main responsibilities:

- Divide a selected Sol range into candidate windows.
- Aggregate available analytical indicators.
- Evaluate file availability.
- Examine data integrity and completeness indicators.
- Incorporate available quality-related indicators.
- Incorporate synchronization diagnostics.
- Handle unavailable metrics transparently.
- Apply configurable ranking weights.
- Generate comparative candidate period rankings.

The ranker is an exploratory comparison component. A higher score does not establish scientific validity.

---

## 5. Desktop Application

MDRPA is planned as a standalone Windows desktop application.

The selected GUI technology is **PySide6**, with **PyQtGraph** for interactive scientific visualizations where appropriate.

The GUI is intended to provide access to the analysis workflow without requiring users to modify Python source files.

### Planned Application Modules

| Module | Responsibility |
|---|---|
| Input Manager | Select and organize MEDA input data |
| Analysis Configuration | Configure Sol ranges and analysis parameters |
| Analysis Center | Start, monitor, and manage analysis executions |
| Results Dashboard | Display analysis summaries and key indicators |
| Reports & Export | Inspect and export generated reports |
| Help / About / Credits | Provide application guidance and project information |

These are planned application responsibilities. Their presence in this document does not imply that the GUI has already been implemented.

### Planned Interface Capabilities

- Structured data tables.
- Analysis progress indicators.
- Temporal coverage charts.
- Product availability summaries.
- Data completeness summaries.
- Synchronization comparisons.
- Candidate period ranking visualizations.
- Report inspection and export.

---

## 6. Input Data Management

MDRPA is intended to support two complementary input methods.

### 6.1 Manual Selection

Planned capabilities include:

- Select individual CSV files.
- Select individual XML files.
- Select multiple files.
- Select complete directories.
- Add or remove selected files.
- Preview filenames, extensions, and file sizes.
- Validate selected inputs before analysis.

### 6.2 Automatic File Discovery

The application is also intended to support discovery from selected input directories.

The discovery workflow identifies:

- Sol directories.
- Available product codes.
- CSV/XML relationships.
- Missing metadata counterparts.
- Unsupported files.
- Potential duplicate files.

Both methods are intended to support analysis of complete datasets or selected subsets.

---

## 7. Analysis Configuration

MDRPA is designed to provide configurable analysis settings.

Planned settings include:

| Setting | Description |
|---|---|
| Input Directory | Location of the selected MEDA dataset |
| Start Sol | First Sol included in the analysis |
| End Sol | Last Sol included in the analysis |
| Candidate Window Size | Number of Sols grouped into each candidate period |
| Synchronization Tolerance | Permitted difference in the selected time coordinate |
| Required Products | Products expected for the analysis |
| Optional Products | Products included when available |
| Ranking Weights | Relative contribution of available ranking indicators |
| Minimum Metrics | Minimum number of available indicators required for ranking |

Example candidate window sizes:

- 5 Sols
- 10 Sols
- 15 Sols
- 20 Sols

Changing the candidate window size changes how periods are grouped and compared. It does not modify the original measurement data.

Configuration management is intended to be centralized rather than independently hardcoded into individual analyzers.

---

## 8. Candidate Period Ranking

A candidate period represents a selected range of consecutive Sols.

For example, with a window size of 10 Sols:

| Candidate | Sol Range |
|---|---|
| Period 1 | Sol 107–116 |
| Period 2 | Sol 117–126 |
| Period 3 | Sol 127–136 |
| Period 4 | Sol 137–146 |

Candidate periods may be compared using available analytical indicators.

### Ranking Dimensions

The ranking workflow may consider:

1. File Availability
2. Data Integrity and Completeness
3. Quality-Related Indicators, when sufficiently supported
4. Synchronization Diagnostics

### Ranking Principles

- Every metric must have a documented calculation method.
- Unavailable metrics must not be replaced with invented values.
- Missing metrics must be handled transparently.
- Ranking weights must be documented and configurable.
- Comparisons must disclose which metrics were available.
- Partial windows must not be treated as equivalent to complete windows.
- Synchronization match rates must not automatically be interpreted as measurement quality.
- A ranking score must not be presented as a scientific certification.

The purpose of ranking is to support candidate selection and further investigation, not to declare a period scientifically valid solely because it receives a higher score.

---

## 9. Project Architecture

MDRPA follows a modular architecture that separates scientific analysis, backend orchestration, run management, graphical presentation, and reporting.

### High-Level Project Structure

```text
MEDA-Data-Research-Period-Analyzer-MDRPA/
│
├── application/
│
├── backend/
│   ├── analyzers/
│   ├── pipeline/
│   ├── reporting/
│   ├── run_manager/
│   ├── validation/
│   └── workers/
│
├── docs/
│
├── gui/
│   ├── analysis/
│   ├── dashboard/
│   ├── dialogs/
│   ├── input_manager/
│   ├── main_window/
│   ├── reports/
│   ├── styles/
│   └── tutorial/
│
├── input/
├── output/
├── packaging/
├── resources/
├── tests/
├── user_data/
│
├── requirements.txt
├── README.md
└── LICENSE
```

This is a high-level structural overview. Individual modules and their implementation status are documented separately.

### Architecture Responsibilities

**Scientific Analyzers**

Perform file discovery, XML parsing, coverage analysis, quality-related examination, synchronization analysis, and candidate period ranking.

**Backend Pipeline**

Coordinates analyzer execution and manages dependencies between analysis stages.

**Run Manager**

Maintains independent analysis runs, unique Run IDs, configurations, metadata, statuses, and run-specific storage.

**Workers and Execution Services**

Support background execution and communication between the backend and the GUI.

**GUI**

Provides input management, configuration controls, progress monitoring, result visualization, and report exploration.

**Reporting**

Organizes generated analysis artifacts and supports structured report access and export.

The GUI must not independently reimplement scientific analysis logic. Backend modules must remain independent of GUI rendering components.

---

## 10. Run Isolation and Data Organization

Each analysis execution must be independently identifiable and stored.

Every run is intended to have:

- A unique Run ID.
- Its own configuration.
- Its own metadata.
- Its own input and output organization.
- Its own execution status and logs.

Repeated analyses of the same Sol range must receive different Run IDs.

Example:

```text
user_data/
└── runs/
    ├── range_100_150_run_001/
    │   ├── input/
    │   ├── output/
    │   ├── config.json
    │   └── run_metadata.json
    │
    └── range_100_150_run_002/
        ├── input/
        ├── output/
        ├── config.json
        └── run_metadata.json
```

The actual run structure is governed by the Run Manager implementation and its integration specification.

Run isolation is intended to prevent accidental mixing or overwriting of data from different executions.

User-generated data must remain separate from the application source and installation directories.

---

## 11. Generated Reports

The analysis workflow uses structured CSV and JSON artifacts.

| Report | Format | Purpose |
|---|---|---|
| File Inventory | CSV | Discovered files and file relationships |
| Metadata Inventory | JSON | Extracted XML metadata |
| Coverage Report | CSV | File-level temporal coverage |
| Coverage Summary | JSON | Coverage summaries |
| Quality Field Report | CSV | Field-level data characteristics |
| Quality Summary | JSON | Quality analysis summary |
| Synchronization File Report | CSV | Timestamp analysis per product |
| Synchronization Pair Report | CSV | Timestamp matching between product pairs |
| Synchronization Summary | JSON | Synchronization overview |
| Period Ranking | CSV | Candidate period comparison |
| Period Ranking Summary | JSON | Ranking configuration and results |

The exact artifact paths are determined by the execution configuration and, eventually, the run-specific output directory.

Reports should preserve traceability between original inputs, analysis settings, and generated results.

---

## 12. Technology Stack

| Technology | Purpose |
|---|---|
| Python | Application and analytical logic |
| PySide6 | Desktop graphical interface |
| PyQtGraph | Interactive scientific visualizations |
| NumPy | Numerical operations |
| Pandas | Tabular data processing where needed |
| PyYAML | Configuration file support |
| lxml | XML processing |
| Python Standard Library | File handling, CSV, JSON, timestamps, and command-line utilities |
| PyInstaller | Planned Windows executable packaging |

The exact dependencies used by each component are defined in `requirements.txt` and the corresponding implementation.

---

## 13. Installation

### Requirements

- Windows is the primary target platform.
- Python 3.10 or newer.
- Sufficient disk space for the selected MEDA data and generated reports.
- Internet access when downloading official NASA/PDS datasets.

### 13.1 Clone the Repository

```bash
git clone https://github.com/AASH010/MEDA-Data-Research-Period-Analyzer-MDRPA.git
```

### 13.2 Enter the Project Directory

```bash
cd MEDA-Data-Research-Period-Analyzer-MDRPA
```

### 13.3 Create a Virtual Environment

```bash
python -m venv .venv
```

### 13.4 Activate the Environment

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 13.5 Install Dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

These steps prepare the Python environment. They do not imply that a complete desktop application or installer is already available.

---

## 14. Current Development Status

MDRPA is under active development.

The scientific analyzer modules have undergone initial implementation and testing. However, the full application architecture, run management, integrated execution workflow, GUI, and packaging must be completed and validated through the approved development process.

The project distinguishes between:

- Implemented functionality.
- Tested functionality.
- Accepted functionality.
- Planned functionality.
- Known limitations.

A module's initial implementation does not mean that the entire application or its scientific outputs have received final validation.

For current implementation details and development decisions, refer to the relevant documents in `docs/`.

---

## 15. Scientific Principles and Limitations

Scientific transparency is a fundamental design principle of MDRPA.

### 15.1 File Availability Is Not Data Completeness

The presence of a CSV file does not establish that its measurements are complete, interpretable, or scientifically valid.

### 15.2 Data Completeness Is Not Measurement Quality

A dataset may contain many numeric values while still having measurement limitations or uncertainty.

### 15.3 Metadata Must Guide Interpretation

Field definitions, measurement units, documented ranges, special constants, and quality indicators must be interpreted using authoritative metadata.

### 15.4 Quality Flags Must Not Be Guessed

Quality-related values must not receive undocumented meanings or be converted into arbitrary quality scores.

Binary values must not automatically be interpreted as `1 = good` and `0 = bad`.

### 15.5 Metadata Warnings Are Not Automatically Measurement Quality Issues

Metadata parsing warnings, missing metadata, and measurement-level quality characteristics must remain distinguishable.

### 15.6 Numeric Range Checks Are Limited

Documented `valid_minimum` and `valid_maximum` values provide numerical range checks. They do not independently establish scientific validity.

### 15.7 Timestamp Interpretation Requires Care

Timestamp parsing must respect the documented time system.

Mission-specific time values must not be converted into another time system without an authoritative reference.

LMST, LTST, UTC, and other time coordinates must not be treated as interchangeable.

### 15.8 Temporal Overlap Does Not Guarantee Identical Sampling

Two MEDA products may overlap in time while having different sampling schedules, frequencies, or missing observations.

Synchronization tolerance must be interpreted in the selected coordinate and must not automatically be described as SI seconds.

### 15.9 MEDA Measurements Are Location-Specific

MEDA observations are measurements collected at the rover's location and measurement times.

They do not represent continuous spatial weather coverage across every geographical grid cell.

In particular, MEDA data availability must not automatically be interpreted as direct environmental validation for every 10 × 10 km MarsWalk Intelligence grid cell.

### 15.10 Candidate Rankings Are Exploratory

A higher candidate period score indicates stronger performance according to the selected metrics and configuration.

It does not independently establish scientific validity or guarantee suitability for every research purpose.

### 15.11 Scientific Validation

Analytical behavior and outputs must be tested against representative official MEDA files and authoritative documentation.

Unverified behavior and unavailable measurements must be reported transparently.

---

## 16. Development Roadmap

MDRPA follows a controlled, phased development process.

The main phases are:

- **P0 — Project Governance:** Establish development rules, documentation responsibilities, and project-wide conventions.
- **P1 — Backend Audit:** Inspect and verify the existing scientific backend.
- **P2 — Run Manager:** Design and implement independent analysis run management.
- **P3 — Pipeline Integration:** Integrate existing analyzers through documented interfaces.
- **P4 — Execution Engine:** Implement background execution, progress reporting, error handling, and safe cancellation.
- **P5 — GUI Foundation:** Establish the desktop application structure and shared interface components.
- **P6 — GUI Modules:** Implement the functional application modules.
- **P7 — Testing and Validation:** Perform technical, integration, regression, and scientific validation.
- **P8 — Packaging and Release:** Prepare and validate the Windows executable and installer.

A phase is not considered complete merely because its files have been created or its code has been written. Required testing, review, and explicit acceptance are mandatory.

---

## 17. Related Project

MDRPA is an independent research utility associated with the broader **MarsWalk Intelligence (MWI)** research initiative.

Its purpose is to investigate and assess MEDA environmental data before selected datasets are considered for subsequent research and data-preparation workflows.

MDRPA is not the core MarsWalk Intelligence application and is maintained as a separate project.

---

## 18. License

This project is licensed under the **MIT License**.

See the [LICENSE](LICENSE) file for details.

The MIT License applies to the project code distributed under this repository. It does not override the terms, attribution requirements, or usage conditions applicable to NASA/PDS datasets and other third-party materials.

---

## 19. Acknowledgments

MDRPA acknowledges the work of NASA, the Mars 2020 mission team, the Perseverance rover team, the MEDA instrument team, and the Planetary Data System (PDS) Atmospheres Node for making scientific mission data and documentation available to the research community.

Their contributions make independent exploration and further scientific investigation of the Martian environment possible.

---

**MEDA Data Research & Period Analyzer (MDRPA)**

*Structured data exploration. Transparent analysis. Evidence-based candidate period evaluation.*