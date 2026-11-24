#!/usr/bin/env python3
"""
nifti2bids_gifmi.py

Convert a subject-organized NIfTI/JSON dataset to a BIDS-like folder structure
using a curated SequenceName/ProtocolName/ImageType mapping table.

Author
------
Prof. Dr. Ir. Pim Pullens

Affiliations
------------
- Department of Medical Imaging, UZ Gent
- Ghent Institute for Functional and Metabolic Imaging (GIfMI),
  UGent CORE Facility
- MEDISIP, Institute of Biomedical Engineering (iBME),
  Faculty of Engineering and Architecture,
  Ghent University

Contact
-------
pim.pullens@ugent.be
pim.pullens@uzgent.be

Development support
-------------------
Microsoft Copilot (GPT-5) was used to assist with software design,
refactoring, documentation, quality control design, and code generation.
All scientific decisions, curation rules, sequence classification logic,
and validation were performed by the author.

Version
-------
1.0.0

Copyright
---------
Copyright (c) 2026 Pim Pullens.
All rights reserved.
"""

import argparse
import csv
import json
import logging
import re
import shutil
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


VERSION = "1.0.0"

REQUIRED_MAPPING_COLUMNS = {
    "SequenceName",
    "ProtocolName",
    "Manufacturer",
    "ImageType",
    "BIDS_datatype",
    "BIDS_suffix",
    "BIDS_entities",
}


def normalize_imagetype(imgtype):
    """Normalize ImageType and remove the ignored SWI token."""
    tokens = str(imgtype).split("+")
    normalized = []
    for token in tokens:
        token = token.strip().upper()
        if token and token != "SWI":
            normalized.append(token)
    return "+".join(normalized)


def image_type_string(value):
    if isinstance(value, list):
        return "+".join(str(item) for item in value)
    return str(value)


def protocol_to_acq(protocol_name):
    """Convert ProtocolName to a short, BIDS-safe acquisition label."""
    text = unicodedata.normalize("NFKD", str(protocol_name)).strip().lower()
    text = text.encode("ascii", "ignore").decode("ascii")

    # Preserve useful decimal measurements as compact labels.
    text = text.replace("0.9mm", "09mm").replace("5.6", "56")
    text = remove_decimal_dots(text)

    # BIDS labels contain letters and numbers only; separator ambiguity is
    # represented by a hyphen that is then collapsed.
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def remove_decimal_dots(text):
    """Remove dots between decimal digits while avoiding regex ambiguity."""
    output = []
    for index, character in enumerate(text):
        if character == ".":
            before = text[index - 1:index]
            after = text[index + 1:index + 2]
            if before.isdigit() and after.isdigit():
                continue
        output.append(character)
    return "".join(output)


def clean_optional(value):
    value = "" if value is None else str(value).strip()
    return "" if value.lower() in {"", "nan", "none", "null"} else value


def read_mapping(mapping_path):
    try:
        with mapping_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ValueError("The mapping CSV has no header row.")

            missing = sorted(REQUIRED_MAPPING_COLUMNS - set(reader.fieldnames))
            if missing:
                raise ValueError(
                    "The mapping CSV is missing required columns: "
                    + ", ".join(missing)
                )

            rows = list(reader)
    except (OSError, csv.Error) as exc:
        raise ValueError(f"Unable to read mapping CSV: {exc}") from exc

    if not rows:
        raise ValueError("The mapping CSV contains no data rows.")

    lookup = {}
    duplicate_keys = []
    invalid_rows = []

    for line_number, row in enumerate(rows, start=2):
        sequence = clean_optional(row["SequenceName"])
        protocol = clean_optional(row["ProtocolName"])
        image_type = normalize_imagetype(row["ImageType"])

        datatype = clean_optional(row["BIDS_datatype"])
        suffix = clean_optional(row["BIDS_suffix"])
        if not datatype or not suffix:
            invalid_rows.append({
                "line": line_number,
                "SequenceName": sequence,
                "ProtocolName": protocol,
                "ImageType": image_type,
                "reason": "Missing BIDS_datatype or BIDS_suffix",
            })
            continue

        key = (sequence, protocol, image_type)
        info = {
            "datatype": datatype,
            "suffix": suffix,
            "entities": clean_optional(row["BIDS_entities"]),
        }

        if key in lookup:
            duplicate_keys.append(
                f"line {line_number}: SequenceName={sequence!r}, "
                f"ProtocolName={protocol!r}, ImageType={image_type!r}"
            )
        else:
            lookup[key] = info

    if duplicate_keys:
        raise ValueError(
            "The mapping CSV contains duplicate exact keys:\n"
            + "\n".join(duplicate_keys)
        )

    return lookup, invalid_rows


def build_bids_name(subject, protocol_name, info):
    parts = [subject, f"acq-{protocol_to_acq(protocol_name)}"]
    if info["entities"]:
        parts.append(info["entities"])
    parts.append(info["suffix"])
    return "_".join(parts)


def unique_bids_name(base_name, used_names):
    if base_name not in used_names:
        used_names.add(base_name)
        return base_name, False

    parts = base_name.split("_")
    suffix = parts[-1]
    prefix = "_".join(parts[:-1])
    run = 2
    while True:
        candidate = f"{prefix}_run-{run}_{suffix}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate, True
        run += 1


def copy_sidecars(source_base, target_base):
    copied = []
    for extension in (".bvec", ".bval"):
        source = Path(str(source_base) + extension)
        if source.exists():
            destination = Path(str(target_base) + extension)
            shutil.copy2(source, destination)
            copied.append(str(destination))
    return copied


def write_tsv(path, fieldnames, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def configure_logging(output_dir, logger):
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "conversion.log"

    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return log_path


def find_nifti(json_file):
    base = Path(str(json_file)[:-5])
    gz = Path(str(base) + ".nii.gz")
    plain = Path(str(base) + ".nii")
    if gz.is_file():
        return gz
    if plain.is_file():
        return plain
    return None


def utc_timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def subject_is_valid(subject):
    return subject.startswith("sub-") and len(subject) > 4


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Convert NIfTI/JSON sidecars to a BIDS-like folder structure "
            f"(nifti2bids_gifmi {VERSION})."
        )
    )
    parser.add_argument("--input", required=True, help="Folder containing sub-* folders")
    parser.add_argument("--mapping", required=True, help="Curated classification CSV")
    parser.add_argument("--output", required=True, help="Destination BIDS folder")
    parser.add_argument("--dry-run", action="store_true", help="Validate without copying")
    parser.add_argument("--json-only", action="store_true", help="Copy JSON sidecars only")
    args = parser.parse_args()

    input_dir = Path(args.input).expanduser().resolve()
    mapping_path = Path(args.mapping).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()

    if not input_dir.is_dir():
        parser.error(f"Input directory does not exist: {input_dir}")
    if not mapping_path.is_file():
        parser.error(f"Mapping CSV does not exist: {mapping_path}")

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        parser.error(f"Cannot create output directory: {exc}")

    logger = logging.getLogger("nifti2bids")
    log_path = configure_logging(output_dir, logger)
    logger.info("nifti2bids_gifmi version %s", VERSION)
    logger.info("Input: %s", input_dir)
    logger.info("Mapping: %s", mapping_path)
    logger.info("Output: %s", output_dir)

    try:
        lookup, invalid_mapping_rows = read_mapping(mapping_path)
    except ValueError as exc:
        logger.error("%s", exc)
        parser.error(str(exc))

    for invalid_row in invalid_mapping_rows:
        logger.warning(
            "Skipped mapping row %d: %s",
            invalid_row["line"],
            invalid_row["reason"],
        )

    converted = []
    unmatched = []
    duplicates = []
    skipped_derived = []
    missing_nifti = []
    manifest = []

    used_names = set()
    used_keep_keys = set()

    subjects = sorted(
        path
        for path in input_dir.iterdir()
        if path.is_dir() and subject_is_valid(path.name)
    )

    if not subjects:
        logger.warning("No valid sub-* folders were found in the input directory.")

    for subject_dir in subjects:
        subject = subject_dir.name
        logger.info("Processing %s", subject)

        for json_file in sorted(subject_dir.rglob("*.json")):
            try:
                with json_file.open("r", encoding="utf-8") as handle:
                    metadata = json.load(handle)
            except json.JSONDecodeError as exc:
                unmatched.append({
                    "subject": subject,
                    "json": str(json_file),
                    "reason": f"Invalid JSON: line {exc.lineno}, column {exc.colno}",
                })
                logger.warning("Invalid JSON %s: %s", json_file, exc)
                continue
            except OSError as exc:
                unmatched.append({
                    "subject": subject,
                    "json": str(json_file),
                    "reason": f"Cannot read JSON: {exc}",
                })
                logger.warning("Cannot read %s: %s", json_file, exc)
                continue

            if not isinstance(metadata, dict):
                unmatched.append({
                    "subject": subject,
                    "json": str(json_file),
                    "reason": "JSON root is not an object",
                })
                continue

            sequence_name = clean_optional(metadata.get("SequenceName"))
            protocol_name = clean_optional(metadata.get("ProtocolName"))
            raw_image_type = image_type_string(metadata.get("ImageType", []))
            image_type = normalize_imagetype(raw_image_type)

            raw_upper = raw_image_type.upper()
            if "DERIVED" in raw_upper and "SWI" not in raw_upper:
                skipped_derived.append({
                    "subject": subject,
                    "json": str(json_file),
                    "SequenceName": sequence_name,
                    "ProtocolName": protocol_name,
                    "ImageType": raw_image_type,
                })
                continue

            key = (sequence_name, protocol_name, image_type)
            info = lookup.get(key)
            if info is None:
                unmatched.append({
                    "subject": subject,
                    "json": str(json_file),
                    "SequenceName": sequence_name,
                    "ProtocolName": protocol_name,
                    "ImageType": image_type,
                    "reason": "No exact mapping found",
                })
                logger.warning("No exact mapping: %s", json_file)
                continue

            nifti_file = None
            if not args.json_only:
                nifti_file = find_nifti(json_file)
                if nifti_file is None:
                    missing_nifti.append({
                        "subject": subject,
                        "json": str(json_file),
                        "reason": "Matching .nii.gz or .nii missing",
                    })
                    unmatched.append({
                        "subject": subject,
                        "json": str(json_file),
                        "reason": "Matching NIfTI missing",
                    })
                    logger.warning("Missing NIfTI for %s", json_file)
                    continue

            used_keep_keys.add(key[:2])

            datatype = info["datatype"]
            target_dir = output_dir / subject / datatype
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                unmatched.append({
                    "subject": subject,
                    "json": str(json_file),
                    "reason": f"Cannot create output folder: {exc}",
                })
                continue

            base_name = build_bids_name(subject, protocol_name, info)
            bids_name, duplicated = unique_bids_name(base_name, used_names)

            if duplicated:
                duplicates.append({
                    "subject": subject,
                    "base_name": base_name,
                    "assigned_name": bids_name,
                    "source_json": str(json_file),
                })
                logger.info("Duplicate name resolved: %s -> %s", base_name, bids_name)

            conversion = {
                "subject": subject,
                "datatype": datatype,
                "source_json": str(json_file),
                "bids_name": bids_name,
            }
            converted.append(conversion)

            if args.dry_run:
                continue

            target_json = target_dir / f"{bids_name}.json"
            try:
                shutil.copy2(json_file, target_json)

                if args.json_only:
                    manifest.append({
                        **conversion,
                        "target_json": str(target_json),
                        "target_nifti": "",
                    })
                    continue

                if nifti_file.suffix == ".gz":
                    nifti_name = f"{bids_name}.nii.gz"
                else:
                    nifti_name = f"{bids_name}.nii"
                target_nifti = target_dir / nifti_name
                shutil.copy2(nifti_file, target_nifti)

                copy_sidecars(
                    Path(str(json_file)[:-5]),
                    target_dir / bids_name,
                )

                manifest.append({
                    **conversion,
                    "target_json": str(target_json),
                    "target_nifti": str(target_nifti),
                })
                logger.info("Converted %s -> %s", json_file.name, bids_name)

            except (OSError, shutil.Error) as exc:
                unmatched.append({
                    "subject": subject,
                    "json": str(json_file),
                    "reason": f"Copy failed: {exc}",
                })
                logger.error("Copy failed for %s: %s", json_file, exc)

    qc_dir = output_dir / "qc"
    qc_dir.mkdir(parents=True, exist_ok=True)

    write_tsv(
        output_dir / "conversion_report.tsv",
        ("subject", "datatype", "source_json", "bids_name"),
        converted,
    )
    write_tsv(
        output_dir / "unmatched.tsv",
        ("subject", "json", "SequenceName", "ProtocolName", "ImageType", "reason"),
        unmatched,
    )
    write_tsv(
        output_dir / "duplicates.tsv",
        ("subject", "base_name", "assigned_name", "source_json"),
        duplicates,
    )

    participants = sorted({row["subject"] for row in converted})
    write_tsv(
        output_dir / "participants.tsv",
        ("participant_id",),
        [{"participant_id": participant} for participant in participants],
    )

    unused_rows = []
    for sequence, protocol, _ in lookup:
        key = (sequence, protocol)
        if key not in used_keep_keys:
            unused_rows.append({
                "SequenceName": sequence,
                "ProtocolName": protocol,
            })

    write_tsv(
        output_dir / "unused_keep_protocols.tsv",
        ("SequenceName", "ProtocolName"),
        unused_rows,
    )

    write_tsv(
        qc_dir / "unmatched.tsv",
        ("subject", "json", "SequenceName", "ProtocolName", "ImageType", "reason"),
        unmatched,
    )
    write_tsv(
        qc_dir / "duplicates.tsv",
        ("subject", "base_name", "assigned_name", "source_json"),
        duplicates,
    )
    write_tsv(
        qc_dir / "missing_nifti.tsv",
        ("subject", "json", "reason"),
        missing_nifti,
    )
    write_tsv(
        qc_dir / "skipped_derived.tsv",
        ("subject", "json", "SequenceName", "ProtocolName", "ImageType"),
        skipped_derived,
    )
    write_tsv(
        qc_dir / "conversion_manifest.tsv",
        ("subject", "datatype", "source_json", "bids_name", "target_json", "target_nifti"),
        manifest,
    )
    write_tsv(
        qc_dir / "unused_keep_protocols.tsv",
        ("SequenceName", "ProtocolName"),
        unused_rows,
    )
    write_tsv(
        qc_dir / "invalid_mapping_rows.tsv",
        ("line", "SequenceName", "ProtocolName", "ImageType", "reason"),
        invalid_mapping_rows,
    )

    dataset_description = {
        "Name": "Converted BIDS Dataset",
        "BIDSVersion": "1.9.0",
        "GeneratedBy": [{
            "Name": "nifti2bids_gifmi",
            "Version": VERSION,
        }],
    }
    with (output_dir / "dataset_description.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(dataset_description, handle, indent=2)
        handle.write("\n")

    summary = {
        "version": VERSION,
        "timestamp": utc_timestamp(),
        "input": str(input_dir),
        "mapping": str(mapping_path),
        "output": str(output_dir),
        "dry_run": args.dry_run,
        "json_only": args.json_only,
        "subjects_found": len(subjects),
        "mapping_rows": len(lookup),
        "invalid_mapping_rows": len(invalid_mapping_rows),
        "converted": len(converted),
        "unmatched": len(unmatched),
        "duplicates": len(duplicates),
        "missing_nifti": len(missing_nifti),
        "skipped_derived": len(skipped_derived),
        "unused_keep_protocols": len(unused_rows),
        "qc_directory": str(qc_dir),
    }
    with (output_dir / "conversion_summary.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")

    with (output_dir / "conversion_summary.txt").open(
        "w", encoding="utf-8"
    ) as handle:
        handle.write(
            f"NIfTI-to-BIDS conversion summary (version {VERSION})\n"
            f"Subjects: {len(subjects)}\n"
            f"Converted: {len(converted)}\n"
            f"Unmatched: {len(unmatched)}\n"
            f"Duplicates resolved: {len(duplicates)}\n"
            f"Missing NIfTI: {len(missing_nifti)}\n"
            f"Derived images skipped: {len(skipped_derived)}\n"
            f"Unused mapping protocols: {len(unused_rows)}\n"
            f"Invalid mapping rows skipped: {len(invalid_mapping_rows)}\n"
            f"QC folder: {qc_dir}\n"
        )

    logger.info("================================")
    logger.info("Conversion complete")
    logger.info("Version: %s", VERSION)
    logger.info("Subjects: %d", len(subjects))
    logger.info("Converted: %d", len(converted))
    logger.info("Duplicates resolved: %d", len(duplicates))
    logger.info("Unmatched: %d", len(unmatched))
    logger.info("Missing NIfTI: %d", len(missing_nifti))
    logger.info("Derived skipped: %d", len(skipped_derived))
    logger.info("Unused mapping protocols: %d", len(unused_rows))
    logger.info("QC folder: %s", qc_dir)
    logger.info("Summary: %s", output_dir / "conversion_summary.txt")
    logger.info("Log: %s", log_path)
    logger.info("================================")

    return 0


if __name__ == "__main__":
    sys.exit(main())
