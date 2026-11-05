# MEDA Data Research & Period Analyzer (MDRPA)

### A Scientific Data Exploration, Validation, and Candidate Period Ranking Platform for NASA Perseverance MEDA Data

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Application](https://img.shields.io/badge/Application-Desktop%20GUI-purple)
![Status](https://img.shields.io/badge/Development-In%20Progress-orange)

---

## Overview

**MEDA Data Research & Period Analyzer (MDRPA)** is an independent scientific research application developed to explore, inspect, validate, and analyze environmental datasets collected by the Mars Environmental Dynamics Analyzer (MEDA) aboard NASA's Perseverance rover.

The project provides a structured analytical workflow for investigating data availability, XML metadata, temporal coverage, data completeness, quality-related indicators, and synchronization across MEDA instrument products.

MDRPA also aims to evaluate and rank candidate observation periods using configurable analytical indicators, helping researchers identify time ranges that may be more suitable for subsequent data preparation and research workflows.

The application is being developed as a standalone desktop tool with an interactive graphical interface for input management, analysis configuration, execution, visualization, and report exploration.

**MDRPA is an analytical support tool. It does not replace scientific validation, official instrument documentation, or expert interpretation.**

---

## Table of Contents

- [Project Overview](#project-overview)
- [Research Objectives](#research-objectives)
- [Data Source](#data-source)
- [Core Analysis Modules](#core-analysis-modules)
- [Desktop Application](#desktop-application)
- [Input Data Management](#input-data-management)
- [Analysis Configuration](#analysis-configuration)
- [Candidate Period Ranking](#candidate-period-ranking)
- [Project Architecture](#project-architecture)
- [Input Data Organization](#input-data-organization)
- [Generated Reports](#generated-reports)
- [Technology Stack](#technology-stack)
- [Installation](#installation)
- [Usage](#usage)
- [Scientific Principles and Limitations](#scientific-principles-and-limitations)
- [Development Roadmap](#development-roadmap)
- [Related Project](#related-project)
- [License](#license)
- [Acknowledgments](#acknowledgments)

---

## Project Overview

Scientific analysis of environmental datasets requires more than simply loading CSV files.

Reliable data assessment involves understanding the original file structure, metadata definitions, measurement timestamps, missing observations, quality indicators, and temporal relationships between different instrument products.

MDRPA is designed to organize these tasks into a modular and reproducible workflow.

The application aims to answer questions such as:

- Which MEDA products are available within a selected Sol range?
- Are the expected CSV and XML files present?
- Which measurement fields and metadata definitions are available?
- How much interpretable temporal coverage does each product provide?
- How many records contain missing or unparseable timestamps?
- How do different MEDA products overlap in time?
- Which candidate periods have stronger data availability and completeness indicators?
- How does changing the analysis configuration affect candidate period rankings?

The application generates structured reports and comparative indicators to support further investigation.

---

## Research Objectives

The main research objectives are:

1. **Dataset Exploration** — Discover and organize MEDA products across selected Sol ranges.
2. **Metadata Inspection** — Extract field definitions and descriptive information from XML metadata.
3. **Temporal Coverage Assessment** — Investigate timestamp availability, missing timestamps, duplicates, and temporal boundaries.
4. **Data Completeness Assessment** — Identify missing, non-numeric, and potentially invalid values.
5. **Synchronization Analysis** — Investigate temporal overlap and timestamp matching between different MEDA products.
6. **Candidate Period Evaluation** — Compare observation windows using configurable analytical indicators.
7. **Reproducible Analysis** — Preserve configurations and generated reports to support repeatable research workflows.
8. **Data Preparation Support** — Provide evidence that can help guide subsequent dataset selection and preparation.

---

## Data Source

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

## Core Analysis Modules

The analytical layer consists of six independent Python modules.

### 1. File Discovery

**Module:** `file_discovery.py`

Responsible for discovering, identifying, and inventorying input files.

Main responsibilities:

- Detect Sol directories.
- Extract Sol numbers from directory and filename patterns.
- Identify MEDA product codes.
- Discover CSV and XML files.
- Match corresponding CSV/XML files.
- Identify missing counterparts.
- Detect duplicate or unsupported files.
- Generate a structured file inventory.

**Primary output:**

`output/file_inventory.csv`

### 2. XML Metadata Parser

**Module:** `xml_parser.py`

Responsible for extracting descriptive metadata and field definitions from XML files.

Main responsibilities:

- Parse XML metadata structures.
- Extract field names and data types.
- Extract field descriptions and measurement units.
- Extract documented valid ranges.
- Preserve special constants.
- Identify potential time-related and quality-related fields.
- Generate a structured metadata inventory.

**Primary output:**

`output/metadata_inventory.json`

### 3. Coverage Analyzer

**Module:** `coverage_analyzer.py`

Responsible for examining file-level and temporal coverage.

Main responsibilities:

- Analyze available CSV products.
- Count valid data records.
- Identify candidate timestamp fields.
- Parse supported timestamp formats.
- Determine first and last interpretable timestamps.
- Count parsed, missing, and duplicate timestamps.
- Summarize product availability across selected Sol ranges.

**Primary outputs:**

- `output/coverage_report.csv`
- `output/coverage_summary.json`

### 4. Quality Analyzer

**Module:** `quality_analyzer.py`

Responsible for examining field-level data characteristics and documented numerical boundaries.

Main responsibilities:

- Identify candidate quality-related fields.
- Examine fields with documented valid ranges.
- Count missing and non-empty values.
- Count numeric and non-numeric values.
- Examine distinct values.
- Identify values outside documented numerical boundaries.
- Preserve quality indicator values without assigning undocumented meanings.

**Primary outputs:**

- `output/quality_field_report.csv`
- `output/quality_summary.json`

### 5. Synchronization Analyzer

**Module:** `synchronization_analyzer.py`

Responsible for examining temporal relationships between different MEDA products.

Main responsibilities:

- Identify candidate timestamp fields.
- Parse supported timestamps.
- Normalize timezone-aware timestamps to UTC.
- Identify temporal overlap between product pairs.
- Count matched and unmatched timestamps.
- Calculate timestamp matching rates.
- Examine timestamp differences.
- Apply a configurable matching tolerance.

**Primary outputs:**

- `output/synchronization_file_report.csv`
- `output/synchronization_pair_report.csv`
- `output/synchronization_summary.json`

### 6. Period Ranker

**Module:** `period_ranker.py`

Responsible for comparing and ranking candidate Sol windows.

Main responsibilities:

- Divide the selected Sol range into candidate windows.
- Aggregate available analytical indicators.
- Evaluate file availability.
- Examine timestamp coverage.
- Examine data completeness.
- Incorporate available synchronization indicators.
- Account for unavailable metrics.
- Apply configurable ranking weights.
- Generate comparative period rankings.

Quality indicators remain unavailable when their supporting measurements cannot be calculated reliably.

**Primary outputs:**

- `output/period_ranking.csv`
- `output/period_ranking_summary.json`

---

## Desktop Application

MDRPA is planned as a standalone desktop application built with **PySide6** and **PyQtGraph**.

The graphical interface is intended to provide access to the analytical workflow without requiring users to modify Python source files.

### Planned Interface Sections

| Section | Purpose |
|---|---|
| Dashboard | Display analysis summaries and key indicators |
| Data Input Manager | Select, add, remove, and validate input files |
| File Inventory | Explore discovered MEDA files |
| Metadata Explorer | Inspect XML metadata and field definitions |
| Coverage Analysis | Explore temporal coverage results |
| Quality Analysis | Examine field-level quality indicators |
| Synchronization Analysis | Investigate temporal relationships |
| Period Ranking | Compare candidate observation periods |
| Analysis Settings | Configure analysis parameters |
| Reports | Explore and export generated results |

### Visualization Capabilities

The interface is intended to support:

- Summary metric cards.
- Interactive data tables.
- Time coverage charts.
- Product availability charts.
- Missing-value summaries.
- Synchronization comparisons.
- Candidate period ranking charts.
- Analysis progress indicators.

---

## Input Data Management

MDRPA is designed to support two complementary input methods.

### 1. Manual File Selection

Users will be able to select files directly through Windows Explorer.

Planned capabilities:

- Select individual CSV files.
- Select individual XML files.
- Select multiple files.
- Select complete directories.
- Add additional files.
- Remove selected files.
- Clear the current selection.
- Preview selected filenames, extensions, and file sizes.
- Validate input files before analysis.

### 2. Automatic File Discovery

The application will also support automatic discovery from selected input directories.

The discovery workflow will identify:

- Sol directories.
- Available product codes.
- CSV/XML relationships.
- Missing metadata counterparts.
- Unsupported files.
- Potential duplicate files.

Both input methods are intended to work together.

Users should be able to analyze an entire dataset or a carefully selected subset.

---

## Analysis Configuration

MDRPA is designed to provide configurable analysis settings through its desktop interface.

Planned settings include:

| Setting | Description |
|---|---|
| Input Directory | Location of the MEDA dataset |
| Output Directory | Destination for generated reports |
| Start Sol | First Sol included in the analysis |
| End Sol | Last Sol included in the analysis |
| Candidate Window Size | Number of Sols grouped into each candidate period |
| Synchronization Tolerance | Maximum permitted timestamp difference for matching |
| Required Products | Products expected in the analysis |
| Optional Products | Products included when available |
| Ranking Weights | Relative contribution of available ranking indicators |
| Minimum Metrics | Minimum number of available indicators required for ranking |

Example candidate window sizes:

- 5 Sols
- 10 Sols
- 15 Sols
- 20 Sols

Changing the window size changes how candidate periods are grouped and compared. It does not modify the original measurement data.

Settings are intended to be managed through a centralized configuration system rather than hardcoded into individual analyzers.

---

## Candidate Period Ranking

One of the primary objectives of MDRPA is to evaluate and compare candidate observation periods.

A candidate period represents a selected range of consecutive Sols.

For example, with a window size of 10 Sols:

| Candidate | Sol Range |
|---|---|
| Period 1 | Sol 107–116 |
| Period 2 | Sol 117–126 |
| Period 3 | Sol 127–136 |
| Period 4 | Sol 137–146 |

Each candidate period can be evaluated using available analytical indicators.

### Planned Ranking Dimensions

1. File Availability
2. Timestamp Coverage
3. Data Completeness
4. Quality Indicators
5. Synchronization Indicators

### Ranking Principles

- Each metric must have a documented calculation method.
- Unavailable metrics must not be replaced with invented values.
- Missing metrics must be handled transparently.
- Ranking weights must be configurable.
- Comparisons must disclose which metrics were actually available.
- Rankings must not be presented as definitive scientific assessments.

The purpose of ranking is to support candidate selection and further investigation, not to declare a period scientifically valid solely because it receives a higher score.

---

## Project Architecture

MDRPA follows a modular architecture that separates analytical processing, application services, and graphical presentation.

```text
MEDA-Data-Research-Period-Analyzer-MDRPA/
│
├── main.py
├── config.yaml
├── requirements.txt
├── README.md
├── LICENSE
│
├── input/
│   ├── sol_0107/
│   ├── sol_0108/
│   └── ...
│
├── analyzers/
│   ├── file_discovery.py
│   ├── xml_parser.py
│   ├── coverage_analyzer.py
│   ├── quality_analyzer.py
│   ├── synchronization_analyzer.py
│   └── period_ranker.py
│
├── services/
│   ├── analysis_runner.py
│   ├── report_loader.py
│   └── config_manager.py
│
├── ui/
│   ├── main_window.py
│   ├── styles.py
│   │
│   ├── pages/
│   │   ├── dashboard.py
│   │   ├── file_inventory.py
│   │   ├── metadata_explorer.py
│   │   ├── coverage_page.py
│   │   ├── quality_page.py
│   │   ├── synchronization_page.py
│   │   ├── ranking_page.py
│   │   └── reports_page.py
│   │
│   └── widgets/
│       ├── metric_card.py
│       ├── chart_widget.py
│       ├── data_table.py
│       └── progress_panel.py
│
└── output/
```

### Architecture Responsibilities

**Analyzers**

Perform data discovery, parsing, statistical examination, temporal analysis, and candidate ranking.

**Services**

Coordinate analyzer execution, manage configurations, handle generated reports, and provide a bridge between the analytical layer and the interface.

**UI**

Provides interactive data management, configuration controls, progress monitoring, visualizations, and report exploration.

This separation is intended to keep analytical logic independent of the graphical interface.

---

## Input Data Organization

MDRPA is designed to preserve original NASA filenames while organizing files into separate Sol directories.

Example:

```text
input/
│
├── sol_0107/
│   ├── ORIGINAL_MEDА_PRODUCT_1.CSV
│   ├── ORIGINAL_MEDА_PRODUCT_1.XML
│   └── ...
│
├── sol_0108/
│   └── ...
│
└── sol_0109/
    └── ...
```

The actual filenames must remain unchanged when importing official NASA products.

The directory structure is intended to simplify file discovery, metadata matching, and Sol-based analysis.

---

## Generated Reports

MDRPA is designed to produce structured reports in CSV and JSON formats.

| Report | Format | Purpose |
|---|---|---|
| File Inventory | CSV | Discovered files and file relationships |
| Metadata Inventory | JSON | Extracted XML metadata |
| Coverage Report | CSV | File-level temporal coverage |
| Coverage Summary | JSON | Product-level coverage summaries |
| Quality Field Report | CSV | Field-level data characteristics |
| Quality Summary | JSON | Quality analysis summaries |
| Synchronization File Report | CSV | Timestamp analysis per product |
| Synchronization Pair Report | CSV | Temporal matching between products |
| Synchronization Summary | JSON | Synchronization overview |
| Period Ranking | CSV | Candidate period comparison |
| Period Ranking Summary | JSON | Ranking configuration and results |

Reports are intended to preserve traceability between the original inputs, analysis settings, and generated results.

---

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Core application and analytical logic |
| PySide6 | Desktop graphical interface |
| PyQtGraph | Interactive scientific visualizations |
| Pandas | Tabular data processing |
| NumPy | Numerical operations |
| PyYAML | Configuration management |
| lxml | XML processing |
| Python Standard Library | File handling, CSV, JSON, timestamps, and command-line utilities |

The analytical modules currently use Python standard-library functionality extensively.

Additional dependencies support the planned desktop interface and broader data-processing workflow.

---

## Installation

### Requirements

- Windows, Linux, or macOS.
- Python 3.10 or newer.
- Internet connection for downloading the official dataset.
- Sufficient disk space for the selected MEDA files and generated reports.

### 1. Clone the Repository

```bash
git clone https://github.com/AASH010/MEDA-Data-Research-Period-Analyzer-MDRPA.git
```

Replace `YOUR_USERNAME` with the actual GitHub account or organization.

### 2. Enter the Project Directory

```bash
cd MEDA-Data-Research-Period-Analyzer-MDRPA
```

### 3. Create a Virtual Environment

```bash
python -m venv .venv
```

### 4. Activate the Environment

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
source .venv/bin/activate
```

### 5. Install Dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

---

## Usage

The analytical modules are currently organized as independent scripts.

The following commands represent the current command-line workflow.

Run them from the project root directory.

### 1. Discover Files

```bash
python analyzers/file_discovery.py
```

### 2. Parse XML Metadata

```bash
python analyzers/xml_parser.py
```

### 3. Analyze Coverage

```bash
python analyzers/coverage_analyzer.py
```

Optional Sol range:

```bash
python analyzers/coverage_analyzer.py --start-sol 107 --end-sol 250
```

### 4. Analyze Data Quality

```bash
python analyzers/quality_analyzer.py
```

### 5. Analyze Synchronization

```bash
python analyzers/synchronization_analyzer.py
```

Example with a custom tolerance:

```bash
python analyzers/synchronization_analyzer.py --tolerance 5
```

### 6. Rank Candidate Periods

```bash
python analyzers/period_ranker.py
```

Example with a 15-Sol candidate window:

```bash
python analyzers/period_ranker.py --window-size 15
```

**Important:** The commands above describe the current individual analyzer execution workflow. A unified desktop execution workflow is part of the planned application development.

Run modules in their required dependency order, and ensure that their prerequisite reports exist before execution.

---

## Scientific Principles and Limitations

Scientific transparency is a fundamental design principle of MDRPA.

### 1. Measurement Quality Is Not the Same as File Availability

The presence of a CSV file does not establish that its measurements are complete, interpretable, or scientifically valid.

### 2. Metadata Must Guide Interpretation

Field definitions, measurement units, valid ranges, special constants, and quality indicators must be interpreted using documented metadata.

### 3. Quality Flags Must Not Be Guessed

Quality-related values must not receive undocumented meanings or be converted into arbitrary quality scores.

### 4. Timestamp Interpretation Requires Care

Timestamp parsing must respect the documented time system.

Numeric mission-specific time values must not be interpreted without an authoritative conversion definition.

Timezone-aware and timezone-naive timestamps must not be compared as though they necessarily represent the same time system.

### 5. Temporal Overlap Does Not Guarantee Identical Sampling

Two MEDA products may overlap in time while having different measurement schedules, sampling frequencies, or missing observations.

### 6. MEDA Measurements Are Location-Specific

MEDA observations are measurements collected at the rover's location and measurement times.

They do not represent continuous spatial weather coverage across every geographical grid cell.

In particular, MEDA data availability must not automatically be interpreted as direct environmental validation for every 10 × 10 km MarsWalk Intelligence grid cell.

### 7. Candidate Rankings Are Analytical Indicators

A higher candidate period score indicates stronger performance according to the selected metrics and configuration.

It does not independently establish scientific validity or guarantee suitability for every research purpose.

### 8. Validation Status

The project is under active development.

Analytical outputs and calculations must be validated against representative official MEDA files before being treated as reliable research results.

---

## Development Roadmap

MDRPA is being developed through the following stages.

- [x] Initial project architecture.
- [x] File discovery module implementation.
- [x] XML metadata parser implementation.
- [x] Coverage analyzer implementation.
- [x] Quality analyzer implementation.
- [x] Synchronization analyzer implementation.
- [x] Candidate period ranker implementation.
- [ ] Comprehensive analyzer code audit.
- [ ] Validation against real NASA MEDA datasets.
- [ ] Cross-module integration testing.
- [ ] Analysis runner service.
- [ ] Report loader service.
- [ ] Centralized configuration manager.
- [ ] Desktop GUI foundation.
- [ ] Manual Windows file selection.
- [ ] Automatic input discovery integration.
- [ ] Interactive analysis configuration.
- [ ] Dashboard and analytical visualizations.
- [ ] Report export and exploration.
- [ ] Full application testing and validation.

The completion status of individual modules refers to initial implementation, not final scientific validation.

---

## Related Project

MDRPA is an independent research utility associated with the broader **MarsWalk Intelligence (MWI)** research initiative.

Its purpose is to investigate and assess MEDA environmental data before selected datasets are considered for subsequent research and data-preparation workflows.

MDRPA is not the core MarsWalk Intelligence application and is maintained as a separate tool.

---

## License

This project is licensed under the **MIT License**.

See the [LICENSE](LICENSE) file for details.

The MIT License applies to the project code distributed under this repository. It does not override the terms, attribution requirements, or usage conditions applicable to NASA/PDS datasets and other third-party materials.

---

## Acknowledgments

MDRPA acknowledges the work of NASA, the Mars 2020 mission team, the Perseverance rover team, the MEDA instrument team, and the Planetary Data System (PDS) Atmospheres Node for making scientific mission data and documentation available to the research community.

Their contributions make independent exploration and further scientific investigation of the Martian environment possible.

---

**MEDA Data Research & Period Analyzer (MDRPA)**

*Structured data exploration. Transparent analysis. Evidence-based candidate period evaluation.*
