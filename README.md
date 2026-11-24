# NIfTI-to-BIDS Conversion Script

## Table of contents

- [NIfTI-to-BIDS Conversion Script](#nifti-to-bids-conversion-script)
  - [Table of contents](#table-of-contents)
  - [Author](#author)
    - [Affiliations](#affiliations)
    - [Contact](#contact)
  - [Software Development Support](#software-development-support)
  - [Version](#version)
  - [Citation](#citation)
  - [Disclaimer](#disclaimer)
  - [Quick summary](#quick-summary)
  - [Requirements](#requirements)
  - [NIfTI conversion](#nifti-conversion)
  - [DICOM to NIfTI Conversion Using dcm2niix](#dicom-to-nifti-conversion-using-dcm2niix)
    - [Recommended Command](#recommended-command)
    - [Parameter Description](#parameter-description)
    - [Example Output](#example-output)
  - [Input layout](#input-layout)
  - [Create the initial mapping table](#create-the-initial-mapping-table)
    - [Requirements](#requirements-1)
    - [Generate the table](#generate-the-table)
    - [Review and curate before conversion](#review-and-curate-before-conversion)
  - [Mapping CSV](#mapping-csv)
  - [Basic usage](#basic-usage)
  - [Command-line options](#command-line-options)
  - [Output structure](#output-structure)
  - [Conversion reports](#conversion-reports)
    - [Summary reports](#summary-reports)
    - [Conversion reports](#conversion-reports-1)
  - [QC outputs](#qc-outputs)
  - [Duplicate names](#duplicate-names)
  - [Existing sidecars](#existing-sidecars)
  - [Suggested review workflow](#suggested-review-workflow)
  - [Validate](#validate)
  - [Script version](#script-version)

## Author

**Prof. Dr. Ir. Pim Pullens**

### Affiliations

- Department of Medical Imaging, UZ Gent
- Ghent Institute for Functional and Metabolic Imaging (GIfMI), UGent CORE Facility
- MEDISIP, Institute of Biomedical Engineering (iBME), Faculty of Engineering and Architecture, Ghent University

### Contact

- pim.pullens@ugent.be
- pim.pullens@uzgent.be

---

## Software Development Support

Parts of this software were developed with assistance from:

**Microsoft Copilot (GPT-5)**

AI assistance was used for:

- software design
- code generation
- refactoring
- documentation
- quality-control workflow design
- validation and testing suggestions

Scientific ownership, sequence curation, BIDS mapping decisions, quality-control criteria, validation procedures, and acceptance of the final implementation remain the responsibility of the author.

---

## Version

Current version: **1.0.0**

---

## Citation

If this software contributes to published work, please cite:

> Pullens P. nifti2bids: conversion of curated clinical MRI datasets to BIDS format. Department of Medical Imaging, UZ Gent; Ghent Institute for Functional and Metabolic Imaging (GIfMI), UGent CORE Facility; MEDISIP, Institute of Biomedical Engineering (iBME), Faculty of Engineering and Architecture, Ghent University.

---

## Disclaimer

This software is intended to assist in the organization and conversion of neuroimaging datasets into BIDS format. Users remain responsible for validating BIDS compliance, verifying metadata correctness, reviewing quality-control outputs, and ensuring the suitability of the resulting dataset for downstream scientific analyses.

---

## Quick summary

This tool helps organize MRI NIfTI files into a consistent folder and filename
structure. You provide the folder containing the scans and a reviewed table
that tells the tool how each scan type should be named.

In brief:

1. Put the scan files into folders named for each participant, such as
   `sub-001`.
2. Create a draft mapping table with `createbidsmappingtable.sh`, then have
   someone familiar with the scans review it. The draft's suggestions are not
   guaranteed to be correct.
3. Run the converter first with `--dry-run` to check what it can match without
   copying scan files.
4. Review the short summary and the files in the `qc/` folder. Fix the mapping
   or source files if needed.
5. Run the converter again without `--dry-run` to create the organized output.

The tool reports files it could not match instead of guessing. Always review
the reports and check the output before using or sharing it. This creates a
BIDS-like structure; it does not replace expert review or formal BIDS
validation.

`nifti2bids_gifmi.py` converts Siemens NIfTI/JSON sidecars organized by subject
into a BIDS-like directory structure.

The script is designed for repeatable, auditable conversions and reports every
conversion decision without requiring neuroimaging expertise for basic use.

## Requirements

- Python 3
- Standard Python libraries only
- Input directories named `sub-*`
- A mapping CSV, normally `sequence_classificationKEEP.csv`

No additional Python packages need to be installed.

## NIfTI conversion

## DICOM to NIfTI Conversion Using dcm2niix

The recommended workflow is to first convert the original DICOM data to NIfTI + JSON sidecar files using **dcm2niix**, and subsequently convert the resulting dataset to BIDS using `nifti2bids.py`.

### Recommended Command

```bash
dcm2niix \
  -b y \
  -ba y \
  -z y \
  -i n \
  -m y \
  -f "%i_%p_%t_%s" \
  -o OUTPUT_DIRECTORY \
  INPUT_DICOM_DIRECTORY
```

### Parameter Description

| Option | Description |
|----------|-------------|
| `-b y` | Generate JSON sidecar files |
| `-ba y` | Anonymize metadata written to JSON files |
| `-z y` | Compress output images as `.nii.gz` |
| `-i n` | Retain all DICOM series, including derived images |
| `-m y` | Merge slices belonging to the same acquisition |
| `-f "%i_%p_%t_%s"` | Filename format: patient identifier, protocol name, acquisition timestamp, and series number |
| `-o` | Output directory |
| `INPUT_DICOM_DIRECTORY` | Directory containing the source DICOM files |

### Example Output

```text
PT5_raw_mprage_tfl3d_sag_1mm_20240314202322_5.nii.gz
PT5_raw_mprage_tfl3d_sag_1mm_20240314202322_5.json

PT5_raw_t2_swi_wave4_2mm_20240314202322_16.nii.gz
PT5_raw_t2_swi_wave4_2mm_20240314202322_16.json
```

This naming convention preserves sufficient provenance (protocol name, acquisition time, and series number) while remaining compatible with subsequent automated BIDS conversion.

## Input layout

The input folder should contain subject folders:

```text
input/
|-- sub-001/
|   |-- acquisition_1.json
|   `-- acquisition_1.nii.gz
`-- sub-002/
    |-- acquisition_2.json
    `-- acquisition_2.nii.gz
```

Each subject folder may contain JSON sidecars in nested folders. The script
looks for matching NIfTI files with either `.nii.gz` or `.nii`.

JSON files must provide these fields:

- `SequenceName`
- `ProtocolName`
- `ImageType`

Here is an example to create the input layout. Adapt to your own input structure (i.e. with Copilot).

```bash
#!/usr/bin/env bash

set -euo pipefail

OUTDIR="NIFTIGZ_ONLY"

mkdir -p "$OUTDIR"

find . -maxdepth 2 -type d -name "*_NIFTIgz" | while read -r dir; do

    parent=$(basename "$(dirname "$dir")")

    # Extract subject number from parent folder
    if [[ "$parent" =~ PT([0-9]+) ]]; then
        subid=$(printf "sub-%03d" "${BASH_REMATCH[1]}")
    else
        echo "WARNING: could not parse $parent"
        continue
    fi

    ln -s "$(realpath "$dir")" "$OUTDIR/$subid"
done
```

## Create the initial mapping table

The helper script `createbidsmappingtable.sh` scans the JSON sidecars in
`NIFTIGZ_ONLY/` and creates `sequence_classification.csv`. It counts identical
combinations of `SequenceName`, `ProtocolName`, `Manufacturer`, and `ImageType`,
then suggests BIDS datatype, suffix, and entities using rules in the shell
script.

### Requirements

- Bash
- [`jq`](https://jqlang.org/) available on your `PATH`
- An `NIFTIGZ_ONLY/` folder in the current working directory, containing the
  subject folders and JSON sidecars used for conversion

### Generate the table

Run the helper from the folder that contains `NIFTIGZ_ONLY/`:

```bash
cd /path/to/MRI_JSON_sidecars
./createbidsmappingtable.sh
```

The generated file is `sequence_classification.csv` in the current directory.
The script has no command-line options; it expects the input folder and output
filename shown above.

### Review and curate before conversion

Treat this file as a draft, not an approved mapping. Review its suggested
datatype, suffix, entities, and comments with someone familiar with the
acquisitions. In particular:

1. Check rows marked `IGNORE` or describing derived images.
2. Fill in or correct the BIDS columns where the script did not identify a
   sequence.
3. Keep only the rows intended for conversion.
4. Save the reviewed table as `sequence_classificationKEEP.csv` (or another
   filename to pass to `--mapping`).

The generated table includes `count` and `Comments` columns in addition to the
mapping fields. These extra columns are retained for review and are not used to
match scans. The converter requires `SequenceName`, `ProtocolName`,
`Manufacturer`, `ImageType`, `BIDS_datatype`, `BIDS_suffix`, and
`BIDS_entities`.

An example `sequence_classificationKEEP.csv` file is included in this package.

## Mapping CSV

The CSV must contain the following columns:

```text
SequenceName
ProtocolName
Manufacturer
ImageType
BIDS_datatype
BIDS_suffix
BIDS_entities
```

The Manufacturer column is required by the table format but is not used during
matching.

Matching is exact on the normalized combination:

```text
(SequenceName, ProtocolName, ImageType)
```

The script removes the `SWI` token from `ImageType` for both the mapping table
and dataset metadata. It does not use relaxed or partial matching.

Derived images are skipped unless their `ImageType` contains `SWI`. Invalid or
incomplete mapping rows are logged and saved in the QC outputs.

## Basic usage

Run a full conversion:

```bash
python3 nifti2bids_gifmi.py \
  --input /path/to/input \
  --mapping sequence_classificationKEEP.csv \
  --output /path/to/output
```

Validate the inputs and matching without copying files:

```bash
python3 nifti2bids_gifmi.py \
  --input /path/to/input \
  --mapping sequence_classificationKEEP.csv \
  --output /path/to/output \
  --dry-run
```

Copy JSON sidecars only:

```bash
python3 nifti2bids_gifmi.py \
  --input /path/to/input \
  --mapping sequence_classificationKEEP.csv \
  --output /path/to/output \
  --json-only
```

`--dry-run` and `--json-only` may be combined.

## Command-line options

| Option | Required | Description |
|---|---:|---|
| `--input` | Yes | Folder containing one or more `sub-*` folders |
| `--mapping` | Yes | Curated sequence classification CSV |
| `--output` | Yes | Destination output folder |
| `--dry-run` | No | Validate and report without copying files |
| `--json-only` | No | Copy JSON sidecars without NIfTI or diffusion sidecars |

## Output structure

A typical output is:

```text
output/
|-- sub-001/
|   `-- anat/
|       |-- sub-001_acq-..._T1w.json
|       `-- sub-001_acq-..._T1w.nii.gz
|-- qc/
|-- conversion.log
|-- conversion_summary.json
|-- conversion_summary.txt
|-- conversion_report.tsv
|-- unmatched.tsv
|-- duplicates.tsv
|-- participants.tsv
|-- unused_keep_protocols.tsv
`-- dataset_description.json
```

The script creates a BIDS-like folder, but its output should be checked for
dataset-specific entity and datatype requirements before publication or formal
BIDS validation.

## Conversion reports

### Summary reports

- `conversion_summary.txt`: Short, human-readable summary.
- `conversion_summary.json`: Machine-readable summary and run settings.
- `conversion.log`: Timestamped processing and warning/error log.
- `dataset_description.json`: Basic BIDS dataset description.

### Conversion reports

- `conversion_report.tsv`: Successfully matched acquisitions.
- `unmatched.tsv`: JSON files that could not be converted.
- `duplicates.tsv`: Filenames that required an added run number.
- `participants.tsv`: Participant IDs found in converted results.
- `unused_keep_protocols.tsv`: Mapping protocols that were not used.

## QC outputs

Detailed quality-control files are written to `qc/`:

| File | Contents |
|---|---|
| `conversion_manifest.tsv` | Source and destination files for copied acquisitions |
| `unmatched.tsv` | All unmatched acquisition details |
| `duplicates.tsv` | Duplicate filename resolutions |
| `missing_nifti.tsv` | JSON files missing a matching `.nii` or `.nii.gz` |
| `skipped_derived.tsv` | Derived acquisitions intentionally skipped |
| `invalid_mapping_rows.tsv` | Mapping rows missing required BIDS fields |
| `unused_keep_protocols.tsv` | Mapping protocols absent from successful matches |

## Duplicate names

If a BIDS name is assigned more than once, the script adds a run entity:

```text
sub-001_acq-example_T1w
sub-001_acq-example_run-2_T1w
sub-001_acq-example_run-3_T1w
```

## Existing sidecars

For diffusion acquisitions, the script copies `.bvec` and `.bval` sidecars when
present. The sidecar names are based on the source JSON/NIfTI basename.

## Suggested review workflow

1. Run with `--dry-run`.
2. Review `conversion_summary.txt`.
3. Review `qc/unmatched.tsv`.
4. Review `qc/invalid_mapping_rows.tsv`.
5. Review `qc/skipped_derived.tsv`.
6. Run without `--dry-run`.
7. Confirm a sample output JSON and NIfTI pair.

## Validate

Use the offical BIDS validator to perform the final check: [https://bids.neuroimaging.io/tools/validator.html](https://bids.neuroimaging.io/tools/validator.html)

`bids-validator BIDS_DATASET`

## Script version

The script reports version `1.0.0` in command-line logs and generated JSON/text
summaries.
