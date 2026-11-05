# Scientific Methodology

**Project:** MEDA Data Research & Period Analyzer (MDRPA)  
**Document:** Scientific Methodology  
**Version:** 1.0 — Proposed  
**Target Branch:** `main`

---

## 1. Purpose and Scientific Scope

This document describes the scientific and analytical principles governing the examination of Mars Environmental Dynamics Analyzer (MEDA) data used by MDRPA.

The project is designed to explore, inspect, and compare candidate observation periods using available MEDA data products and their associated metadata.

The application provides exploratory evidence to support research planning and further scientific investigation.

It does not certify scientific validity, establish instrument health, or independently determine whether a period is suitable for a particular scientific conclusion.

The methodology distinguishes between:

- Data availability.
- Measurement and timestamp completeness.
- Structural metadata integrity.
- Documented quality-related information.
- Measurement uncertainty information.
- Temporal synchronization.
- Exploratory candidate-period ranking.

These dimensions must remain distinguishable throughout the analysis.

## 2. Data and Metadata Principles

### 2.1 CSV Measurement Data

CSV files contain the observation records examined by the analyzers.

Their interpretation depends on the corresponding product metadata and XML field definitions.

The application must not assume that:

- Every CSV contains a header row.
- CSV column order always matches XML field order.
- Every product has the same sampling schedule.
- Every available file contains complete measurements.
- Every numeric value represents a scientifically valid observation.

### 2.2 XML Metadata

XML metadata provides documented information about product structure and fields.

The XML parser extracts information including:

- Product identification.
- Sol and source-file information.
- Table layout metadata.
- Field names and field numbers.
- Data types.
- Descriptions and units.
- Documented numerical bounds.
- Special constants.
- Candidate time and quality-related field names.

Metadata extraction does not automatically establish the scientific meaning of every field.

### 2.3 CSV-to-XML Column Mapping

Measurement analysis depends on safely mapping CSV columns to their corresponding XML field definitions.

The current implementation supports several mapping situations:

1. Exact header matching.
2. Reordered unique headers.
3. Strict positional mapping for validated duplicate XML field names.
4. Narrowly validated WS field-name aliases.
5. Positional mapping when XML explicitly declares that no header exists.

Ambiguous mappings must not be used for measurement calculations.

Known exceptions must be handled through narrowly validated rules rather than general assumptions or automatic modification of source metadata.

## 3. Data Availability and Coverage

### 3.1 File Availability

File availability describes whether expected product files are present in the examined Sol range.

The inventory analyzer identifies supported CSV and XML files and records information such as:

- Sol number.
- Product code.
- Filename.
- File extension.
- File size.
- CSV/XML pairing information.

The existence of a file does not establish that its measurements are complete or scientifically valid.

### 3.2 Measurement Coverage

Coverage analysis examines the contents of individual CSV files using their XML metadata.

The current analyzer reports:

- CSV row count.
- Selected time field and time-axis kind.
- Parsed timestamps.
- Missing timestamps.
- Invalid timestamps.
- Duplicate timestamps.
- Out-of-order timestamps.
- Temporal span.
- Median positive adjacent timestamp step.
- Detected timestamp gaps.
- Numeric values.
- Missing numeric values.
- Invalid numeric values.
- Column-mapping status.

Coverage is a descriptive assessment of the available records and their structure.

It is not a direct measurement of sensor performance or scientific validity.

### 3.3 Timestamp Gap Detection

The current coverage analyzer uses the median of positive adjacent timestamp steps as a reference interval.

The configured gap threshold is:

\[
T_{\text{gap}} = F \times
\operatorname{median}(\text{positive adjacent steps})
\]

Where:

- \(F\) is the configured `gap_factor`.
- The current default is `2.5`.
- The factor must be finite and greater than 1.

A positive adjacent step greater than this threshold is counted as a detected gap.

This is a relative gap-detection method.

**Important limitations:**

- It does not establish why a gap occurred.
- It does not prove that the instrument stopped operating.
- It does not establish the expected sampling schedule.
- It does not provide a defensible estimate of missing measurement duration.
- The resulting coordinate differences are not necessarily physical SI seconds for every supported time axis.

The reported sum of detected gaps must therefore not be interpreted as a scientifically established missing-duration estimate.

## 4. Time-Axis Methodology

### 4.1 General Rule

Time values must be interpreted according to their documented or identifiable time-axis kind.

The application must not silently combine incompatible time coordinates.

The current shared time utilities support:

| Time kind | Current treatment |
|---|---|
| SCLK | Finite numeric spacecraft-clock coordinate |
| UTC | Timezone-aware ISO-8601 values normalized to UTC epoch seconds |
| LMST | Linear Mars-sol coordinate |
| LTST | Nominal Sol/local-clock coordinate |
| ISO naive | Timezone-unspecified ISO coordinate |

Time parsing success does not independently prove the scientific correctness of the original timestamp.

### 4.2 SCLK

SCLK is parsed as a finite numeric coordinate.

The current implementation does not convert SCLK into UTC.

A numeric SCLK value must not be treated as UTC merely because it can be represented as a floating-point number.

### 4.3 UTC

UTC values are accepted only when the ISO-8601 timestamp includes timezone information.

Timezone-aware values are normalized to UTC epoch seconds.

Timezone-naive timestamps are not silently assumed to be UTC.

### 4.4 LMST

Local Mean Solar Time is represented using a linear Mars-sol coordinate.

The current implementation uses:

\[
1\ \text{Sol} = 88775.244\ \text{Earth seconds}
\]

This value is used as a coordinate scale for LMST processing.

It is not used to convert LMST into UTC.

The resulting coordinate is suitable for the current application's intended ordering and interval analysis, subject to the limitations of the selected representation.

### 4.5 LTST

Local True Solar Time is represented by the current implementation as a nominal Sol/local-clock coordinate.

LTST is true solar time and does not advance uniformly relative to elapsed SI time.

Consequently:

- It must not be treated as a precise elapsed-time scale.
- Its coordinate differences must not automatically be interpreted as physical elapsed seconds.
- It must not be converted to UTC without an authoritative conversion method.

### 4.6 Time-Axis Selection

The current default axis preference is:

1. SCLK.
2. UTC.
3. LMST.
4. LTST.
5. ISO naive.

This is a software selection preference, not a scientific ranking of time systems.

The selected time field and time-axis kind must remain visible in analytical reports.

A change to the default preference requires review because it can affect coverage and synchronization results.

## 5. Data Integrity Indicators

The current implementation examines two broad numerical dimensions:

### 5.1 Timestamp Integrity Indicators

These describe the distribution of successfully parsed, missing, and invalid timestamp values.

The current ranker calculates:

\[
I_t =
\frac{N_{\text{parsed}}}
{N_{\text{parsed}} + N_{\text{missing}} + N_{\text{invalid}}}
\times 100
\]

Where:

- \(N_{\text{parsed}}\) is the number of successfully parsed timestamps.
- \(N_{\text{missing}}\) is the number of missing timestamps.
- \(N_{\text{invalid}}\) is the number of invalid timestamps.

This indicator describes timestamp parsing completeness.

It does not establish sensor uptime or scientific correctness.

### 5.2 Numeric Value Integrity Indicators

The current ranker calculates:

\[
I_v =
\frac{N_{\text{numeric}}}
{N_{\text{numeric}} + N_{\text{missing}} + N_{\text{invalid}}}
\times 100
\]

Where the counts represent the numeric measurement values examined by the coverage analyzer.

This indicator describes numeric-value completeness and successful numeric parsing.

It does not establish that the measurements are physically correct or scientifically valid.

### 5.3 Combined Data Integrity

The current ranker combines available timestamp and numeric-value indicators using configurable internal weights.

The default internal weights are:

| Component | Default Weight |
|---|---:|
| Timestamp integrity | 1.0 |
| Numeric-value integrity | 1.0 |

If one component is unavailable, it is not fabricated as zero.

The remaining available positive weights are normalized.

These indicators are descriptive software metrics, not a validated scientific measure of instrument integrity.

## 6. Quality-Related Metadata and Measurement Uncertainty

### 6.1 Candidate-Based Field Identification

The Quality Analyzer uses documented field names and descriptions to identify possible categories.

The current implementation distinguishes:

- `quality_field_candidate`
- `operational_context_flag_candidate`
- `measurement_uncertainty`
- `range_check`

These categories are based on field metadata and keyword rules.

They are candidates for examination, not authoritative scientific classifications.

A field may belong to more than one category when it meets multiple independent selection rules.

### 6.2 Quality Flags

A field containing a quality-related name or description may be identified as a quality candidate.

However, the application must not infer the meaning of a Quality Flag from its name alone.

In particular, it must not assume:

- Binary values mean good/bad.
- A value of 1 always means valid.
- A value of 0 always means invalid.
- A generic status field represents measurement quality.

Authoritative product documentation is required before assigning scientific meaning to a flag.

### 6.3 Operational and Context Fields

Operational and context candidates are reported separately from quality-related candidates.

Examples may include fields describing operating modes, deployment state, mechanisms, heaters, motors, or instrument context.

An operational state is not automatically a measurement-quality verdict.

### 6.4 Measurement Uncertainty

The analyzer identifies fields whose documented wording suggests uncertainty-related information.

It does not independently:

- Calculate uncertainty.
- Interpret uncertainty conventions.
- Combine uncertainty fields into a universal score.
- Determine whether a measurement is scientifically acceptable.

Uncertainty must retain its documented meaning and units.

### 6.5 Documented Numeric Bounds

The current analyzer extracts `valid_minimum` and `valid_maximum` from XML field metadata where available.

For fields with at least one documented numerical bound, values can be counted as:

- Below the declared minimum.
- Above the declared maximum.

These checks are limited to the documented XML bounds.

A value outside a declared range is flagged for review.

It is not automatically classified as scientifically invalid.

Likewise, a value inside the declared range is not automatically scientifically valid.

Special constants are not automatically treated as missing values by the current quality-analysis methodology.

## 7. Temporal Synchronization

### 7.1 Purpose

Synchronization analysis examines how closely timestamp observations from different MEDA products correspond within a common temporal interval.

It is intended to describe temporal matching between available product records.

It does not establish that two measurements are scientifically equivalent or that their instruments have identical sampling behavior.

### 7.2 Compatible Time Axes

Pair comparisons require both products to use the same time-axis kind.

The current implementation does not attempt automatic conversion between different time-axis kinds.

If the axes are incompatible, the comparison is reported as incompatible rather than forcing a match.

### 7.3 Common Temporal Interval

For two timestamp series, the comparison interval is determined by their overlapping coordinate range.

Only observations within the common interval are included in the matching calculation.

If there is no overlap, the comparison is reported as having no temporal overlap.

### 7.4 One-to-One Matching

The synchronization analyzer uses one-to-one timestamp occurrence matching under a configured absolute tolerance.

Each timestamp occurrence may participate in at most one match.

Duplicate timestamp occurrences are retained as separate observations.

The current implementation uses a two-pointer matching method for sorted one-dimensional timestamp values.

The matching procedure does not silently reuse one timestamp occurrence for multiple matches.

### 7.5 Synchronization Indicators

The analyzer reports:

- Number of observations in each series within the common interval.
- Number of matched timestamp occurrences.
- Unmatched observations in each series.
- Match rate for the first series.
- Match rate for the second series.
- Match rate relative to the sparser series.
- Mean and maximum absolute match difference.
- Common interval information.

The sparser-series match rate is:

\[
R_s =
\frac{N_{\text{matched}}}
{\min(N_1,N_2)}
\times 100
\]

Where \(N_1\) and \(N_2\) are the observation counts in the common interval.

### 7.6 Tolerance Interpretation

Tolerance is applied in the selected time coordinate.

It must not automatically be interpreted as physical SI seconds.

This is particularly important for SCLK, LMST, LTST, and timezone-naive coordinates.

The configured tolerance must be recorded and considered when interpreting synchronization results.

### 7.7 Sampling-Schedule Limitations

Different products may have different sampling schedules.

A low match rate does not automatically establish a malfunction or poor measurement quality.

A high match rate does not prove scientific equivalence.

Synchronization rates must be interpreted in the context of:

- Product sampling schedules.
- Common temporal coverage.
- Selected time axis.
- Matching tolerance.
- Number of observations.
- Product-specific observation behavior.

Synchronization is a diagnostic dimension, not a universal quality score.

## 8. Candidate Period Construction

The Period Ranker divides the selected Sol range into candidate windows.

The current default window size is 10 Sols.

Window construction and Sol-range selection are software configuration choices.

They do not establish a scientifically optimal observation duration.

Each candidate window is evaluated using the available per-Sol metrics.

The ranker distinguishes:

- Full windows.
- Partial windows.
- Windows with insufficient available metrics.
- Rankable windows.

Partial windows are retained in the report for transparency but are not ranked against full candidate windows.

## 9. Exploratory Ranking Methodology

### 9.1 Ranking Dimensions

The current Period Ranker uses four metric dimensions:

1. File availability.
2. Data integrity.
3. Quality indicators.
4. Synchronization.

The default weights are:

| Metric | Default Weight |
|---|---:|
| File Availability | 0.20 |
| Data Integrity | 0.45 |
| Quality Indicators | 0.15 |
| Synchronization | 0.20 |

These weights are configurable software parameters.

They are not scientifically calibrated constants and must not be presented as validated scientific importance factors.

### 9.2 File Availability

File availability is calculated against the configured required product set.

The current default required products are:

- ATS
- PS
- RDS
- RHS
- TIRS
- WS

ENG is optional by default and does not affect the default file-availability score.

The required product set may be explicitly configured.

The availability score describes the presence of configured products, not the completeness or scientific validity of their measurements.

### 9.3 Data Integrity

Data integrity uses the available timestamp and numeric-value completeness indicators described earlier.

The ranker does not interpret successful parsing as proof of measurement validity.

### 9.4 Quality Indicators

The current ranking quality indicator is based only on values checked against documented XML numerical bounds.

It is not calculated from undocumented Quality Flag meanings.

If no suitable documented numerical bounds are available, this metric may be unavailable.

An unavailable quality indicator must not be fabricated as zero or interpreted as evidence that every measurement is valid.

### 9.5 Synchronization

The synchronization metric uses available analyzed pair-level sparser-series match rates.

It is affected by product sampling schedules, overlap, time-axis selection, and tolerance.

It must not be interpreted as a universal synchronization quality measure.

### 9.6 Unavailable Metrics and Weight Normalization

Not every metric is necessarily available for every Sol or candidate window.

A metric is considered available for a window only when its available Sol count meets the configured minimum Sol fraction.

Unavailable metrics are excluded from the weighted calculation.

The remaining available positive weights are renormalized.

A missing metric is therefore not equivalent to a score of zero.

The minimum metric requirement must be respected.

It must not be reduced merely to force a ranking result.

### 9.7 Comparison Groups

Candidate windows are ranked only against windows with the same available positively weighted metric signature.

A rank from one comparison group is not directly comparable to a rank from another group.

A single global best candidate is reported only when there is one comparison group.

When multiple groups exist, the application must present their best candidates separately.

### 9.8 Meaning of the Exploratory Score

The final score is a weighted combination of available metric scores.

It is an exploratory comparison indicator.

It does not represent:

- Scientific certainty.
- Instrument health.
- Measurement accuracy.
- Measurement precision.
- Environmental representativeness.
- Mission-level data validation.
- Fitness for a particular scientific hypothesis.

Candidate periods require further scientific review before research use.

## 10. Spatial and Observation Context

MEDA measurements are observations made at the rover location and at the times represented by the available records.

The existence of measurements during a Sol or time interval does not establish continuous spatial weather coverage across an entire geographical area.

File availability, temporal coverage, and synchronization must not be presented as proof of spatially continuous environmental observations.

Any future spatial analysis must use an explicitly documented spatial methodology and appropriate supporting data.

## 11. Interpretation and Reporting Rules

All analytical reports and GUI summaries must preserve the distinction between:

- Observed values.
- Missing values.
- Invalid or unparseable values.
- Structural metadata warnings.
- Candidate field classifications.
- Documented range-check findings.
- Unavailable metrics.
- Exploratory scores.

The application must not hide unavailable metrics or silently replace them with zero.

Warnings and limitations must remain visible where they affect interpretation.

The application must retain enough run configuration and source-report information to trace a ranking result back to its inputs.

## 12. Scientific Limitations

The current methodology has important limitations:

1. Keyword-based field classification does not establish authoritative scientific meaning.
2. Numeric parsing does not establish physical correctness.
3. XML-declared bounds do not establish universal scientific validity.
4. Timestamp parsing does not establish sensor uptime.
5. Timestamp gap detection does not establish missing measurement duration.
6. Different product sampling schedules affect synchronization results.
7. Time-axis coordinates have different interpretation constraints.
8. Ranking weights are configurable and not scientifically calibrated.
9. Candidate-window rankings depend on the available metric set.
10. Partial windows are not directly ranked against full windows.
11. Product availability does not establish measurement completeness.
12. The ranking does not certify a period for scientific use.

These limitations must remain part of the project's documentation and user-facing interpretation.

## 13. Methodology Change Control

Any change to the scientific or analytical methodology must be separately reviewed.

A proposed change must identify:

- The affected analyzer or shared utility.
- The current behavior.
- The proposed behavior.
- The scientific reason for the change.
- The expected effect on existing reports.
- Required regression tests.
- Any change to metric interpretation or ranking behavior.

Changes to scientific interpretation must not be introduced as incidental GUI or integration work.

Where an authoritative MEDA or PDS documentation source is required, it must be identified and reviewed before implementing the corresponding interpretation.

## 14. Related Documentation

- `README.md` — Project overview and objectives.
- `docs/development_guide.md` — Development workflow and change control.
- `docs/architecture.md` — System architecture.
- `docs/analyzer_documentation.md` — Analyzer interfaces and technical behavior.
- `docs/backend_integration_specification.md` — Backend integration contracts.
- `docs/user_guide.md` — End-user instructions.

## 15. Governing Principle

**MDRPA provides exploratory evidence for examining and comparing MEDA observation periods. It must preserve the distinction between data availability, completeness, documented metadata, measurement uncertainty, temporal synchronization, and scientific validity. No exploratory score or ranking may be presented as scientific certification.**